import asyncio
import os
from typing import Dict, Any

from agenticblocks.core.graph import WorkflowGraph
from agenticblocks.runtime.executor import WorkflowExecutor
from agenticblocks.blocks.llm.agent import AgentInput

from .memgpt import OpalaMemGPTAgentBlock
from .profiles import infer_system_prompt
from . import terminal as T

class ProfileExecutorStrategy:
    def __init__(self, model: str, profile_data: Dict[str, Any]):
        self.model = model
        self.profile_data = profile_data

    async def run(self, user_request: str, history: str, **kwargs) -> str:
        session = kwargs.get("session")
        store = kwargs.get("store")
        project_path = getattr(session, "project_path", ".") if session else "."
        plan_path = os.path.join(project_path, "plan.md")
        
        import yaml
        
        # Write the profile as a YAML block inside plan.md
        profile_yaml = yaml.dump({"tasks": self.profile_data.get("tasks", {})}, allow_unicode=True, sort_keys=False)
        plan_content = f"# Execution Profile Plan\n\nEdite as tarefas abaixo (formato YAML) conforme necessário e salve o arquivo.\n\n```yaml\n{profile_yaml}\n```\n"
        
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(plan_content)
            
        T.info(f"Perfil de execução salvo como plano em '{plan_path}'.")
        T.ask("Edite o arquivo se necessário, salve, e pressione Enter para continuar (ou digite /cancel para abortar)")
        
        # Read the file back
        with open(plan_path, "r", encoding="utf-8") as f:
            updated_content = f.read()
            
        # Extract YAML block
        import re
        yaml_match = re.search(r"```yaml\n(.*?)\n```", updated_content, re.DOTALL)
        if yaml_match:
            try:
                updated_data = yaml.safe_load(yaml_match.group(1))
                if updated_data and "tasks" in updated_data:
                    self.profile_data["tasks"] = updated_data["tasks"]
            except Exception as e:
                T.warning(f"Falha ao interpretar o YAML editado: {e}. Usando o profile original.")

        # Setup tools and VCS
        from .vcs import get_vcs_strategy
        from .config import get_git_strategy
        vcs_strategy = get_vcs_strategy(get_git_strategy(), project_path)
        vcs_strategy.setup()
        
        from .tools import set_project_context, get_available_tools
        if session and store:
            set_project_context(session, store)
            
        agent_tools = get_available_tools() + vcs_strategy.get_tools()

        T.info("Construindo DAG de Execução do Profile...")
        
        graph = WorkflowGraph()
        tasks = self.profile_data.get("tasks", {})
        
        # 1. First pass: Add all blocks
        for task_id, task_data in tasks.items():
            desc = task_data.get("description", "")
            sys_prompt = task_data.get("system_prompt")
            if not sys_prompt:
                sys_prompt = await infer_system_prompt(task_id, desc, self.model)
            
            # For each task, we create an OpalaMemGPTAgentBlock.
            # We can limit its heartbeats based on llm_params if provided, else use default 10.
            llm_params = task_data.get("llm_params", {})
            
            allowed_tools_names = task_data.get("allowed_tools", [])
            if allowed_tools_names:
                task_tools = [t for t in agent_tools if getattr(t, "name", "") in allowed_tools_names or getattr(t, "__name__", "") in allowed_tools_names]
            else:
                task_tools = agent_tools
                
            block = OpalaMemGPTAgentBlock(
                name=task_id,
                model=self.model,
                system_prompt=sys_prompt,
                tools=task_tools,
                max_heartbeats=llm_params.get("max_heartbeats", 50),
                **{k:v for k,v in llm_params.items() if k != "max_heartbeats"}
            )
            graph.add_block(block)
        
        # 2. Second pass: Connect edges based on depends_on
        for task_id, task_data in tasks.items():
            depends_on = task_data.get("depends_on", [])
            for dep in depends_on:
                graph.connect(dep, task_id)
        
        T.info("Iniciando execução do Grafo...")
        
        executor = WorkflowExecutor(graph)
        
        # We start the entry points with the initial user prompt + history
        initial_input = {"prompt": f"{history}\n\n[USER REQUEST]\n{user_request}\n[END USER REQUEST]"}
        
        import asyncio
        import time
        from rich.live import Live
        from .orchestrator import _build_progress_panel
        from .tools import AGENT_PROGRESS
        
        AGENT_PROGRESS.heartbeat = 0
        AGENT_PROGRESS.last_tool = "DAG Executor Started"
        AGENT_PROGRESS.start_time = time.monotonic()
        
        finished = [False]
        result_holder = []
        error_holder = []
        
        async def _run_executor():
            try:
                ctx = await executor.run(initial_input=initial_input)
                result_holder.append(ctx)
            except Exception as e:
                error_holder.append(e)
            finally:
                finished[0] = True

        run_task = asyncio.create_task(_run_executor())
        total_max_hb = sum(t.get("llm_params", {}).get("max_heartbeats", 50) for t in self.profile_data.get("tasks", {}).values())

        with Live(_build_progress_panel(AGENT_PROGRESS, total_max_hb), refresh_per_second=4, transient=False) as live:
            AGENT_PROGRESS.live_context = live
            try:
                while not finished[0]:
                    live.update(_build_progress_panel(AGENT_PROGRESS, total_max_hb))
                    await asyncio.sleep(0.25)
            except KeyboardInterrupt:
                finished[0] = True
                run_task.cancel()
                error_holder.append(RuntimeError("Interrompido pelo usuário. A execução do Perfil (DAG) não pôde ser completada."))
            finally:
                AGENT_PROGRESS.live_context = None
                if not live.is_started:
                    live.start()
                live.update(_build_progress_panel(AGENT_PROGRESS, total_max_hb))
            
        if error_holder:
            return f"Profile execution failed with error: {str(error_holder[0])}"

            
        ctx = result_holder[0]
        final_report = "### Profile Execution Completed\n\n"
        for task_id, node_result in ctx.results.items():
            if node_result.error:
                final_report += f"#### {task_id} (FAILED)\nError: {node_result.error}\n\n"
            elif node_result.output and hasattr(node_result.output, "response"):
                final_report += f"#### {task_id}\n{node_result.output.response}\n\n"
                
        return final_report
