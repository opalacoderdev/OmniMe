import sys
import os
sys.path.append(r'c:\Users\gilza\projetos\OpalaCoder\OpalaCoder')
from opalacoder.project import ProjectStore

store = ProjectStore(db_path=r'c:\Users\gilza\projetos\OpalaCoder\OpalaCoder\test2.db')
store.create(
    name="test-scratch",
    mode="plan",
    model="ollama/gemma4:31b-cloud",
    project_name="Test Scratch",
    project_path=r"c:\Users\gilza\OpalaCoderTestScratch",
    api_base="https://meu-ollama.com",
    api_key="sk-123"
)

with open(r"c:\Users\gilza\OpalaCoderTestScratch\.env", "r") as f:
    print(f.read())
