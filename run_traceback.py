import asyncio
import os
import sys

from opalacoder.projects import load_project
from opalacoder.config import T

async def run():
    sys.argv = ["main.py", "--project", "/home/gilzamir/micalc"]
    project = load_project("/home/gilzamir/micalc")
    from opalacoder.workflow_orchestrator import WorkflowOrchestratorStrategy
    orchestrator = WorkflowOrchestratorStrategy(model="gemini/gemini-3.5-flash")
    
    try:
        summary = await orchestrator.run(
            "os botões da calculadora não funcionam",
            history="",
            session=None,
            store=None,
            project_skills=project.skills
        )
        print("SUCCESS:", summary)
    except Exception as e:
        print("EXCEPTION RAISED:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run())
