import sys
import pexpect
import os

def run():
    env = os.environ.copy()
    env["GEMINI_API_KEY"] = "AIzaSyDbtNjKm17d21h9ImCAd9i1vLivFhId414"
    child = pexpect.spawn(".env/bin/python main.py ", encoding="utf-8", env=env)
    child.logfile = sys.stdout
    child.expect("What would you like to do?")
    child.sendline("2")
    child.expect("OpalaCoder")
    child.sendline("os botões da calculadora não funcionam")
    child.expect("Pressione Enter")
    child.sendline("sim")
    child.expect(pexpect.EOF, timeout=120)

run()
