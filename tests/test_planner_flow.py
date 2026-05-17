import asyncio
import os
import sys

# Add parent directory to path to import abcode
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from abcode.agents import (
    make_skill_selector,
    make_landscape_planner,
    make_context_extractor,
    make_executor_block,
    make_aggregator,
    DEFAULT_MODEL
)
from abcode.skills import get_relevant_skills_llm, SCOPE_ORCHESTRATOR
from agenticblocks.blocks.llm.agent import AgentInput
from pydantic import BaseModel
from abcode.executor import CodePlanExecutorInput, _build_task
from abcode.subplan import Subplan

async def run_flow_test():
    print("="*60)
    print("🚀 ABCODE INFORMATION FLOW TEST")
    print("="*60)
    
    model = DEFAULT_MODEL
    user_request = "crie um app de calculadora"
    print(f"\n[USER REQUEST]: {user_request}\n")
    
    # ---------------------------------------------------------
    # 1. SKILL ROUTER (Orchestrator Scope)
    # ---------------------------------------------------------
    print("\n--- 1. SKILL ROUTER (Planner Phase) ---")
    skills_context = await get_relevant_skills_llm(model, user_request, scope=SCOPE_ORCHESTRATOR)
    print("Output from Skill Router:")
    print(skills_context if skills_context else "(None)")
    
    # ---------------------------------------------------------
    # 2. LANDSCAPE PLANNER
    # ---------------------------------------------------------
    print("\n--- 2. LANDSCAPE PLANNER ---")
    panorama_prompt = f"USER REQUEST: {user_request}\n\n{skills_context}"
    planner = make_landscape_planner(model)
    print("Sending prompt to Planner:")
    print(panorama_prompt)
    
    plan_result = await planner.run(AgentInput(prompt=panorama_prompt))
    plan_text = plan_result.response
    print("\nPlanner Output:")
    print(plan_text)
    
    # ---------------------------------------------------------
    # 3. DECOMPOSER
    # ---------------------------------------------------------
    print("\n--- 3. DECOMPOSER ---")
    from abcode.structured import decompose_to_subplans
    
    print("Calling decompose_to_subplans with instructor...")
    dec_result = await decompose_to_subplans(plan_text, model)
    subplans_data = dec_result.subplans
    print(f"\nExtracted {len(subplans_data)} subplans.")
    
    if not subplans_data:
        print("No subplans extracted. Exiting test.")
        return

    # Convert to standard Subplan schemas
    from abcode.subplan import Subplan as CoreSubplan
    subplans = [
        CoreSubplan(
            id=sp.id,
            phase=sp.phase,
            objective=sp.objective,
            prerequisites=sp.prerequisites,
            steps=sp.steps,
            completion_criterion=sp.completion_criterion,
        )
        for sp in subplans_data
    ]

    # ---------------------------------------------------------
    # 4. EXECUTOR FLOW & CONTEXT EXTRACTOR
    # ---------------------------------------------------------
    print("\n--- 4. EXECUTOR & CONTEXT EXTRACTOR FLOW ---")
    executor = make_executor_block(model)
    context_extractor = make_context_extractor(model)
    
    # We will only simulate the first 2 subplans to keep the test short
    shared_state_value = "No previous steps executed yet. Project is starting from scratch."
    results = {}
    
    for i, sp in enumerate(subplans[:2]):
        print(f"\n>>> EXECUTING SUBPLAN {i+1}: {sp.phase} - {sp.objective}")
        
        task_prompt = _build_task(sp, user_request, shared_state_value, "", cwd="/mock/cwd", project_dir=".")
        print("\n[PROMPT INJECTED INTO EXECUTOR]:")
        print(task_prompt)
        
        # We will mock the execution output instead of actually running code to prevent side effects
        mock_output = ""
        if i == 0:
            mock_output = "Code executed successfully. Project initialized."
        else:
            mock_output = "Files updated. No errors."
            
        print("\n[MOCK RAW EXECUTION LOG]:", mock_output)
        
        # Context Extractor
        print("\n[RUNNING CONTEXT EXTRACTOR]")
        extraction_prompt = (
            f"CURRENT GLOBAL PROJECT STATE:\n{shared_state_value}\n\n"
            f"RAW LOG OUTPUT FROM JUST COMPLETED STEP ({sp.id}):\n{mock_output}"
        )
        print("Context Extractor Prompt:\n" + extraction_prompt)
        
        ext_res = await context_extractor.run(AgentInput(prompt=extraction_prompt))
        shared_state_value = ext_res.response
        print("\nContext Extractor Output (NEW SHARED STATE):\n" + shared_state_value)
        
        results[sp.id] = mock_output
        
    # ---------------------------------------------------------
    # 5. AGGREGATOR
    # ---------------------------------------------------------
    print("\n--- 5. AGGREGATOR ---")
    summary = "\n\n".join(
        f"=== {sp_id} ===\n{output}" for sp_id, output in results.items()
    )
    agg_prompt = (
        f"ORIGINAL REQUEST: {user_request}\n\n"
        f"SUBPLAN RESULTS:\n{summary}"
    )
    print("Aggregator Prompt:\n" + agg_prompt)
    
    aggregator = make_aggregator(model)
    agg_result = await aggregator.run(AgentInput(prompt=agg_prompt))
    print("\nAggregator Output:")
    print(agg_result.response)
    
    print("\n" + "="*60)
    print("✅ TEST FINISHED")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(run_flow_test())
