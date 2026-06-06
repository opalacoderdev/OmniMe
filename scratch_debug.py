import sys
import os
sys.path.append(r'c:\Users\gilza\projetos\OpalaCoder\OpalaCoder')
from opalacoder.project import ProjectStore

store = ProjectStore(db_path=r'c:\Users\gilza\projetos\OpalaCoder\OpalaCoder\test_debug.db')
store.create(
    name="test-debug",
    mode="plan",
    model="ollama/gemma4:31b-cloud",
    project_name="Test Debug",
    project_path=r"c:\Users\gilza\OpalaCoderTestDebug",
    api_base="https://ollama.com/",
    api_key="bac0bac509554ebf91e6ace5bb48cd6c.9fABX6vSdCyY_aFYNwKthvqO"
)

with open(r"c:\Users\gilza\OpalaCoderTestDebug\.env", "r") as f:
    print(f.read())
