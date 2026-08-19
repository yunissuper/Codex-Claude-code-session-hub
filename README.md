# Codex-Claude-code-session-hub 🚀

> **A visual WebUI & workspace manager for Claude Code and Codex CLI sessions with full-text search, turn-based swimlanes, and one-click resume.**

A lightweight, zero-dependency visual interface to browse, search, inspect, and resume your local **Claude Code** and **Codex** CLI sessions organized by project workspaces.

---

## ✨ Features

- 📂 **Workspace-Aware Aggregation**: Automatically maps and groups sessions by project directory instead of arbitrary hash folders.
- ⚡ **Turn-Based Swimlane Navigation**: Interactive turn capsules representing prompt + model execution steps with single-click jump and keyboard shortcuts (`P` for previous, `N` for next).
- 🔍 **Multi-Level & Full-Text Search**: Instant search by prompt, session ID, git branch, or deep full-text indexing inside session transcripts.
- 🛠️ **Deep Step Inspection**: Renders structured user prompts, model responses, tool calls, and execution outputs clearly.
- 📋 **One-Click Resume Command**: Quick-copy ready-to-run `cd <project> && claude --resume <id>` / `codex resume <id>` commands.
- 🌓 **Dark / Light Theme Support**: Modern midnight dark & clean light modes with local preference persistence.

---

## 📦 Quick Start

### 1. Installation

```bash
git clone https://github.com/<your-username>/Codex-Claude-code-session-hub.git
cd Codex-Claude-code-session-hub
pip install -r requirements.txt
```

### 2. Run Locally

```bash
python3 app.py
```

By default, SessionHub listens on `http://127.0.0.1:20089`. Open your browser and explore your CLI history!

### 3. Environment Variables (Optional)

```bash
export PORT=8080               # Custom port (Default: 20089)
export CLAUDE_HOME=~/.claude   # Custom Claude directory
export CODEX_HOME=~/.codex     # Custom Codex directory
```

---

## 📄 License

[MIT License](LICENSE)
