# OmniMe

**OmniMe** is your ultimate AI-powered assistant and intelligent agent, built to supercharge your development workflow. Whether you're brainstorming new ideas, writing complex features, or squashing bugs, OmniMe adapts to your needs with an incredibly flexible and powerful architecture. 

Designed with freedom in mind, OmniMe seamlessly supports both cloud-based and local LLMs—giving you full control over your code and privacy. It shines exceptionally well with local models powered by **Ollama**, allowing you to harness state-of-the-art AI without leaving your machine.

---

## Why Choose OmniMe?

🚀 **Your Personal AI Agent**
OmniMe isn't just an autocomplete tool; it's a fully-fledged AI agent that understands your project context. It works alongside you to handle diverse coding tasks, from interactive planning to automated bug fixing.

🧠 **Persistent Memory & Context**
Never repeat yourself. OmniMe features a persistent memory system that remembers your project's unique quirks, design decisions, and past conversations. It maintains focus, ensuring that the AI has exactly the context it needs, right when it needs it.

🛠️ **Flexible, Skill-Based Architecture**
Tailor your assistant to your exact workflow. OmniMe uses a highly modular "Skills" system. Equip your agent with specific abilities—like web research, advanced refactoring, or custom scripts—allowing it to tackle different tasks seamlessly using specialized sub-agents. 

☁️ **Cloud or Local: You Decide**
Enjoy the best of both worlds. Connect to powerful cloud models or run completely offline with local LLMs. OmniMe is heavily optimized for **Ollama**, making it incredibly easy to run powerful open-weights models locally on your own hardware.

---

## Getting Started

### Installation

#### Windows (1-Click Install)
Open your PowerShell and run the following command to download and install OmniMe instantly:
```powershell
irm https://raw.githubusercontent.com/omnimedev/OmniMe/main/install.ps1 | iex
```

#### Python / Pip

Install OmniMe directly via pip:

```bash
pip install omnime
```

Or run it from source:

```bash
git clone https://github.com/omnimedev/OmniMe
cd OmniMe
python -m venv .env
source .env/bin/activate          # Linux/macOS
# .env\Scripts\activate           # Windows

# Install OmniMe dependencies
pip install -r requirements.txt
```

### Running OmniMe

OmniMe comes with a beautiful, integrated Web-Based GUI that works seamlessly across platforms:

```bash
python main.py
```

*Don't like GUIs? OmniMe also supports an interactive CLI REPL and a headless JSON protocol server!*

---

## Deep Dive: How It Works

Curious about what powers OmniMe under the hood? Want to learn about our MemGPT orchestrator, shadow git versioning, and modular skill designs?

👉 **[Read the Technical Overview](docs/overview.md)**

---

## Community & License

OmniMe is proudly open source and available under the **MIT** license.

*   **Repository**: [https://github.com/omnimedev/OmniMe](https://github.com/omnimedev/OmniMe)
