# TukiCode

<div align="center">
  <img src="./media/tukilogo.png" alt="TukiCode Logo" width="100"/>
  <h3>Stable Release v1.3.4</h3>
  <p>
    <a href="https://github.com/tuki-labs/tukicode/stargazers">
      <img src="https://img.shields.io/github/stars/tuki-labs/tukicode?style=for-the-badge&logo=github&logoColor=white&color=2997ff&labelColor=0d0d0d" alt="Stars"/>
    </a>
    <a href="https://github.com/tuki-labs/tukicode/releases/latest">
      <img src="https://img.shields.io/github/v/release/tuki-labs/tukicode?style=for-the-badge&logo=rocket&logoColor=white&color=2997ff&labelColor=0d0d0d&label=release" alt="Release"/>
    </a>
    <a href="https://github.com/tuki-labs/tukicode/blob/main/LICENSE">
      <img src="https://img.shields.io/badge/license-MIT-2997ff?style=for-the-badge&logo=opensourceinitiative&logoColor=white&labelColor=0d0d0d" alt="License"/>
    </a>
    <br/>
    <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=0d0d0d" alt="Python"/>
    <img src="https://img.shields.io/badge/rust-engine-CE422B?style=for-the-badge&logo=rust&logoColor=white&labelColor=0d0d0d" alt="Rust"/>
    <img src="https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-555?style=for-the-badge&logo=linux&logoColor=white&labelColor=0d0d0d" alt="Platform"/>
  </p>
</div>

**TukiCode** is an open-source CLI coding agent built in Python & Rust. It runs locally with Ollama or in the cloud with OpenRouter, Gemini, and Anthropic. It features a fully asynchronous architecture designed for high performance and responsiveness.

---

## What's New

- **Rust Native Engine (`tuki_native`)** - Replaces performance-critical Python operations (file system, code searching, terminal I/O) with zero-cost Rust bindings for maximum speed.
- **Multiple Tool Calls** - The agent accepts several tool calls per turn and executes them sequentially. Native code search uses Rayon to search files in parallel.
- **Prompt Caching** - Native support for Anthropic context caching, slashing token costs and radically improving Time To First Token (TTFT).
- **Smart Background Shell** - Long-running commands no longer fail due to timeouts; they are transparently relegated to a background process (with smart Anti-Loop monitoring) while the UI continues showing live progress.
- **True Cross-Platform** - The prompt engine dynamically detects your OS (Windows, macOS, Linux) to adapt shell commands and paths automatically.
- **Optimized ReAct Loop** - Context memory compression is now non-blocking (async), avoiding UI freezes. Context bloat is prevented by truncating large tool outputs, and the anti-loop mechanism is stricter to save API calls.
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
git clone https://github.com/tuki-labs/tukicode.git
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

## Working Modes

TukiCode has three distinct operating modes, selectable via tabs in the TUI. Each routes your input through a different pipeline in `core/controller.py`.

| Mode | Tab | Pipeline | Best For |
|---|---|---|---|
| **Chat** | Chat Mode | `AgentLoop.run_turn()` directly | Quick questions, isolated fixes, explanations |
| **Plan** | Plan Mode | `Planner` → shows steps → **asks confirmation** → `Executor` | Controlled multi-step tasks where you want to review before execution |
| **Build** | Build Mode | `Planner` → **shows steps** → `Executor` immediately | Autonomous end-to-end project generation without interruptions |

### Chat Mode

The agent receives your message and enters the ReAct loop directly. It thinks, calls tools, observes results, and loops until it produces a `FinalResponse`. No structured plan is generated — the model decides each action on the fly.

### Plan Mode

1. Your message is sent to `Planner.generate_plan()`, which calls the LLM and returns a JSON array of atomic steps.
2. The plan is displayed and the agent **pauses**, asking `"Do you want to execute this plan? (y/n)"`.
3. If confirmed, `Executor.execute_plan()` runs each step sequentially via `AgentLoop.run_turn()`, with tool evidence and a separate structured review before completing each step. Unverified steps block dependent work; interrupted steps remain pending. Transport retries only occur before any tool is invoked.

### Build Mode

1. If there is a pending plan in `planner_state.json`, execution resumes from the last pending step.
2. If there is no existing plan, `Planner.generate_plan()` is called automatically. The generated plan is **displayed** in the chat before execution starts.
3. `Executor.execute_plan()` runs immediately — **no confirmation is asked**.

> **When to use Build vs Plan:** Use **Plan** when you want to review and approve the strategy first. Use **Build** when you trust the agent to scaffold autonomously and want speed.

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
| `Ctrl+↑` | Restore the last submitted message for editing, without sending it |

---

## Requirements

- Python 3.11+
- One of the following:
  - **Ollama** running locally (`ollama serve`)
  - API key for **OpenRouter**, **Gemini**, or **Anthropic**

---

## Rust Native Engine (`tuki_native`)

`tuki_native` is a native extension written in Rust that compiles and integrates directly into TukiCode (which is written in Python) using a library called PyO3.

In simple terms: it allows TukiCode to execute its heaviest tasks using the extreme power and speed of Rust, while maintaining the ease of use and asynchronous architecture of Python for business logic and AI.

### Why was it created?

Python is excellent for orchestrating AI agents and making asynchronous network requests, but it is slow for CPU-intensive and input/output (I/O) tasks. Before `tuki_native`, operations such as:

- Reading and searching through thousands of code files in a large project.
- Building the directory tree of a complete repository.
- Cleaning and parsing hundreds of lines of text from a terminal (ANSI codes, colors, cursor movements).

...would block Python's main thread or take too long, making TukiCode feel somewhat slow in large repositories. `tuki_native` eliminates these bottlenecks by providing zero-cost bindings, making the agent respond almost instantly in these critical operations.

### How is it structured inside?

The source code in `tuki_native/src/` is divided into highly optimized modules:

#### 1. File System Module (`fs.rs`)
It is responsible for traversing the hard drive ultra-fast using Rust's `walkdir` library.
- **`get_project_tree`**: Generates the project map/tree instantly. It automatically filters heavy and useless folders for the context (like `node_modules`, `.git`, `venv`, `target`, etc.).
- **`find_files`**: Finds files by glob match or extension in milliseconds, skipping ignored folders at the OS level to save resources.
- **`list_dir`**: Lists directory contents with much higher efficiency than Python's `os.listdir`.

#### 2. Search Module (`search.rs`)
- **`search_code`**: Replaces slow searches with pure Python regular expressions. It uses Rust's regular expression engine (`regex`) to search for text or patterns within the user's code. It is capable of crawling safely, respecting limits and filtering by extensions, returning fragments with context lines.

#### 3. Terminal/PTY Module (`pty.rs`)
TukiCode's interactive terminal generates a lot of "visual noise" (control codes, carriage returns, ANSI colors). Cleaning this in Python using `re.sub()` in each execution of the agent loop was very expensive.
- **Ultra-fast cleaning**: Contains functions like `strip_control_sequences`, `strip_ansi`, and `truncate_output`.
- **Memory Optimization**: Uses `OnceLock` to pre-compile regular expressions in memory (cached) only once when the program starts. When Python calls these functions, the CPU cost is practically zero.

---

## Optimized ReAct Loop

TukiCode incorporates a highly optimized asynchronous reasoning loop to prevent bottlenecks and UI freezes, especially in large projects:

- **Asynchronous Memory Compression:** When the conversation history fills up, the agent summarizes it in a 100% non-blocking manner, displaying a visual indicator without halting the application.
- **Context Bloat Prevention:** Massive tool outputs (like reading thousands of lines or listing giant directories) are automatically truncated to a manageable size before being saved to the LLM's history. This keeps the "Time To First Token" (TTFT) extremely low and reduces costs.
- **Realistic Token Estimation:** The engine uses algorithms tuned for source code (which has abundant symbols and keywords) to calculate the actual tokens in context, preventing token limit errors.
- **Strict Anti-Loop:** If the AI model makes a mistake and enters a blind loop repeating the same failed tool, the engine interrupts it on the second failed attempt, injecting a corrective message and saving expensive API calls.

---

## Architecture Summary

```
tuki.py              <- CLI entry point (Typer)
tuki_native/         <- High-performance Rust extension (PyO3)
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

## Step verification

Plan/Build verification requires observed tool results and an additional model review (one API call per step). It fails closed when evidence or the reviewer is unavailable. This review reduces false completion but is not a proof of correctness; run project-specific tests as part of each step. Risk limits and approval frequency are independent settings.

## OpenRouter setup

`tuki config --setup` and `/setup` link directly to [API key creation](https://openrouter.ai/settings/keys). They query the public catalog using `coding-high-to-low` (Artificial Analysis coding index) and filter for tool-capable chat models. Unscored models appear last according to OpenRouter; this ordering does not guarantee performance on a particular task.

Recommendations show base input/output prices per million tokens, context length and up to three free alternatives. Choose by number in the CLI or select a model in the TUI. The catalog lookup sends no API key and consumes no model tokens. During outages, the last cached catalog is explicitly labelled with its timestamp. Without a usable cache, manual model entry remains available with a compatibility warning.

### First launch and access checks

`tuki` or `tuki chat` starts setup until configuration has been completed. Cancelling setup does not mark it complete. New installations store settings in a writable user directory; existing configuration paths and editable checkouts are preserved.

Before saving an OpenRouter selection, setup validates the API key and requests a synthetic native tool call. The returned call is inspected and never executed; no project files are sent. The check allows up to 256 output tokens at the selected model's normal pricing and quota. Access is checked again when starting an OpenRouter chat session.

Access rejection returns to model selection; rejected credentials request a replacement key. Network errors can be retried or abandoned without overwriting the previous configuration. There is no automatic switch to a paid model. Provider availability can still change after validation; later errors retain the service's actual explanation.
