# TukiCode

![TukiCode Logo](./media/tukilogo.png)

**TukiCode** is an open-source CLI coding agent built in Python. It runs locally with Ollama or in the cloud with OpenRouter, Gemini, and Anthropic. It features a fully asynchronous architecture designed for high performance and responsiveness.

---

## What's New

- **Asynchronous Architecture** - All LLM clients use native async methods (httpx, asyncio) for non-blocking execution and faster streaming.
- **MVC Separation** - Business logic, AI model switching, and database interactions are isolated in a dedicated Controller, completely separated from the UI layer.
- **Structured Planner** - The agent's planner strictly enforces JSON structured outputs to generate precise, atomic step-by-step implementation plans.
- **Full TUI** - Fullscreen interface (Textual) with chat panel, file explorer, and Live Console.
- **Interactive Terminal (PTY)** - Real pseudo-terminal for long-running servers and interactive commands.
- **Multi-Provider Support** - Ollama (local), OpenRouter, Gemini, Anthropic.

---

## Installation

### Windows (PowerShell)

```powershell
iwr https://tukicode.site/api/install.ps1 | iex
```

Downloads `tuki.exe` to `%LOCALAPPDATA%\TukiCode\bin` and adds it to your PATH.

### macOS

```bash
curl -fsSL https://tukicode.site/api/install.sh | bash
```

**First run on macOS:** If you see a security warning, run:
```bash
xattr -d com.apple.quarantine ~/.local/bin/tuki
```

### Linux

```bash
curl -fsSL https://tukicode.site/api/install.sh | bash
```

Both macOS and Linux install `tuki` to `~/.local/bin` and update your shell profile automatically.

### From source (any OS)

```bash
git clone https://github.com/sb4ss/tukicode.git
cd tukicode
pip install -r requirements.txt
python tuki.py chat
```

---

## Quick Start

```bash
# 1. Configure your AI provider
tuki config --setup

# 2. Start the agent
tuki chat
```

---

## Configuration

```bash
tuki config --setup     # Interactive wizard
tuki config             # Show current configuration
tuki config --model     # Change model only
```

### Recommended free models (via OpenRouter)

| Model | Notes |
|---|---|
| `tencent/hy3-preview:free` | Recommended: best tool-calling on free tier |
| `moonshotai/kimi-k2.5` | Fast reasoning |
| `deepseek/deepseek-chat-v3.2` | Strong coding tasks |

> TukiCode requires models with **native tool-calling support** for full agent functionality.

---

## Chat Commands

| Command | Description |
|---|---|
| `/help` | List all available commands |
| `/setup` | Open configuration wizard inside the chat |
| `/model` | Switch AI model |
| `/autonomy [low\|medium\|high]` | Control how often the agent asks for confirmation |
| `/risk [low\|medium\|high]` | Adjust risk sensitivity for tool execution |
| `/copy [n]` | Copy code block `n` from the last response |
| `/history` | Show recent sessions |
| `/clear` | Clear the chat log |
| `/exit` | Exit and save the session |

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+S` | Emergency stop: halt the current agent execution |
| `Ctrl+B` | Toggle the Live Console panel |
| `Ctrl+L` | Clear chat log |

---

## Requirements

- Python 3.10+
- One of the following:
  - **Ollama** running locally (`ollama serve`)
  - API key for **OpenRouter**, **Gemini**, or **Anthropic**

---

## Architecture Summary

```
tuki.py              <- CLI entry point (Typer)
core/
  controller.py      <- TukiController (Business Logic and LLM Management)
agent/
  loop.py            <- ReAct reasoning loop (Async)
  planner.py         <- Structured JSON output planner
  executor.py        <- Step-by-step async plan executor
  clients...         <- Async API Clients
tools/
  registry.py        <- Tool registration and dispatch
ui/
  app.py             <- Textual TUI application
config.py            <- TOML configuration manager
```

For deeper technical documentation, see [ARCHITECTURE.md](./ARCHITECTURE.md).
