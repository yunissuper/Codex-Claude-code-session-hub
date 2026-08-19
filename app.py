#!/usr/bin/env python3
"""
SessionHub - Visual WebUI & Session Manager for Claude Code and Codex CLI
"""
import os
import json
import glob
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="SessionHub - Claude Code & Codex Viewer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLAUDE_BASE = os.path.expanduser(os.getenv("CLAUDE_HOME", "~/.claude"))
CODEX_BASE = os.path.expanduser(os.getenv("CODEX_HOME", "~/.codex"))

def clean_system_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)
    text = re.sub(r'<local-command-stdout>.*?</local-command-stdout>', '', text, flags=re.DOTALL)
    return text.strip()

def get_claude_sessions() -> List[Dict[str, Any]]:
    sessions = []
    project_dirs = glob.glob(os.path.join(CLAUDE_BASE, "projects", "*"))
    for pdir in project_dirs:
        if not os.path.isdir(pdir):
            continue
        folder_name = os.path.basename(pdir)
        if folder_name == "memory":
            continue
        norm_path = "/" + folder_name.strip("-").replace("-", "/") if folder_name.startswith("-") else folder_name

        jsonl_files = glob.glob(os.path.join(pdir, "*.jsonl"))
        for jf in jsonl_files:
            sid = os.path.splitext(os.path.basename(jf))[0]
            try:
                st = os.stat(jf)
                mtime = st.st_mtime
                size_kb = round(st.st_size / 1024, 1)
            except Exception:
                continue

            first_prompt = ""
            user_turn_count = 0
            git_branch = ""
            cwd = norm_path

            try:
                with open(jf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                            t = item.get("type")
                            if t == "user":
                                msg = item.get("message", {})
                                content = msg.get("content") if isinstance(msg, dict) else msg
                                is_tool_res = False
                                if isinstance(content, list):
                                    for c in content:
                                        if isinstance(c, dict) and c.get("type") == "tool_result":
                                            is_tool_res = True
                                            break
                                if not is_tool_res:
                                    user_turn_count += 1
                                    if not first_prompt:
                                        if isinstance(content, list):
                                            for c in content:
                                                if isinstance(c, dict) and c.get("type") == "text":
                                                    first_prompt = c.get("text", "")
                                                    break
                                        elif isinstance(content, str):
                                            first_prompt = content
                            if not git_branch and item.get("gitBranch"):
                                git_branch = item.get("gitBranch")
                            if item.get("cwd"):
                                cwd = item.get("cwd")
                        except Exception:
                            continue
            except Exception:
                pass

            first_prompt_clean = clean_system_tags(first_prompt)
            summary = first_prompt_clean[:180] + ("..." if len(first_prompt_clean) > 180 else "") if first_prompt_clean else "(No prompt)"

            sessions.append({
                "id": sid,
                "engine": "claude",
                "project": cwd,
                "project_name": os.path.basename(cwd.rstrip("/")) or "root",
                "folder_raw": folder_name,
                "file_path": jf,
                "mtime": mtime,
                "time_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": size_kb,
                "msg_count": user_turn_count,
                "summary": summary,
                "git_branch": git_branch,
                "resume_cmd": f"claude --resume {sid}"
            })
    return sessions

def get_codex_sessions() -> List[Dict[str, Any]]:
    sessions = []
    session_files = glob.glob(os.path.join(CODEX_BASE, "sessions", "**", "*.jsonl"), recursive=True)
    for jf in session_files:
        sid = os.path.splitext(os.path.basename(jf))[0]
        if sid.startswith("rollout-"):
            sid_clean = sid.split("-")[-5:]
            sid_display = "-".join(sid_clean) if len(sid_clean) >= 5 else sid
        else:
            sid_display = sid

        try:
            st = os.stat(jf)
            mtime = st.st_mtime
            size_kb = round(st.st_size / 1024, 1)
        except Exception:
            continue

        first_prompt = ""
        user_turn_count = 0
        cwd = os.path.expanduser("~")
        git_branch = ""

        try:
            with open(jf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        payload = item.get("payload", {})
                        ptype = item.get("type")
                        if ptype == "session_meta":
                            cwd = payload.get("cwd", cwd)
                            git_branch = payload.get("git_branch", "")
                        elif ptype == "event_msg":
                            msg_type = payload.get("type")
                            if msg_type == "user_message":
                                user_turn_count += 1
                                if not first_prompt:
                                    first_prompt = payload.get("message", "") or payload.get("text", "")
                    except Exception:
                        continue
        except Exception:
            pass

        first_prompt_clean = clean_system_tags(first_prompt)
        summary = first_prompt_clean[:180] + ("..." if len(first_prompt_clean) > 180 else "") if first_prompt_clean else "(Codex session)"

        sessions.append({
            "id": sid,
            "engine": "codex",
            "project": cwd,
            "project_name": os.path.basename(cwd.rstrip("/")) or "root",
            "folder_raw": "codex",
            "file_path": jf,
            "mtime": mtime,
            "time_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_kb": size_kb,
            "msg_count": user_turn_count,
            "summary": summary,
            "git_branch": git_branch,
            "resume_cmd": f"codex resume {sid_display}"
        })
    return sessions

@app.get("/api/sessions")
def list_sessions(
    engine: str = Query("all", pattern="^(all|claude|codex)$"),
    project: Optional[str] = None,
    q: Optional[str] = None
):
    all_sessions = []
    if engine in ["all", "claude"]:
        all_sessions.extend(get_claude_sessions())
    if engine in ["all", "codex"]:
        all_sessions.extend(get_codex_sessions())

    all_sessions.sort(key=lambda x: x["mtime"], reverse=True)

    projects = {}
    for s in all_sessions:
        p = s["project"]
        projects[p] = projects.get(p, 0) + 1

    filtered = all_sessions
    if project:
        filtered = [s for s in filtered if s["project"] == project]
    if q:
        query = q.lower()
        filtered = [
            s for s in filtered
            if query in s["id"].lower()
            or query in s["project"].lower()
            or query in s["summary"].lower()
            or query in s.get("git_branch", "").lower()
        ]

    return {
        "total": len(filtered),
        "projects": projects,
        "sessions": filtered
    }

@app.get("/api/search_full")
def search_full(q: str = Query(..., min_length=2), engine: str = "all"):
    target_sessions = []
    if engine in ["all", "claude"]:
        target_sessions.extend(get_claude_sessions())
    if engine in ["all", "codex"]:
        target_sessions.extend(get_codex_sessions())

    target_sessions.sort(key=lambda x: x["mtime"], reverse=True)

    query = q.lower()
    matches = []
    for s in target_sessions:
        jf = s["file_path"]
        try:
            with open(jf, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if query in content.lower():
                    idx = content.lower().find(query)
                    start = max(0, idx - 60)
                    end = min(len(content), idx + 140)
                    snippet = "..." + content[start:end].replace("\n", " ") + "..."
                    s_copy = dict(s)
                    s_copy["match_snippet"] = snippet
                    matches.append(s_copy)
        except Exception:
            continue

    return {"total": len(matches), "sessions": matches}

@app.get("/api/session/{engine}/{session_id}")
def get_session_detail(engine: str, session_id: str):
    file_path = None
    if engine == "claude":
        for pdir in glob.glob(os.path.join(CLAUDE_BASE, "projects", "*")):
            target = os.path.join(pdir, f"{session_id}.jsonl")
            if os.path.exists(target):
                file_path = target
                break
    elif engine == "codex":
        for p in glob.glob(os.path.join(CODEX_BASE, "sessions", "**", f"{session_id}.jsonl"), recursive=True):
            file_path = p
            break

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Session file not found")

    turns = []
    curr_turn = None

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if engine == "claude":
                        t = data.get("type")
                        if t == "user":
                            msg = data.get("message", {})
                            content = msg.get("content") if isinstance(msg, dict) else msg
                            is_tool_res = False
                            tool_res_text = ""
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "tool_result":
                                        is_tool_res = True
                                        tool_res_text = str(item.get("content", ""))
                                        break
                            if not is_tool_res:
                                user_text = content if isinstance(content, str) else ""
                                if isinstance(content, list):
                                    user_text = "\n".join([x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"])
                                if curr_turn:
                                    turns.append(curr_turn)
                                clean_prompt = clean_system_tags(user_text)
                                curr_turn = {
                                    "turn_id": len(turns) + 1,
                                    "user_prompt": clean_prompt or "(Prompt)",
                                    "user_raw": user_text,
                                    "timestamp": data.get("timestamp"),
                                    "steps": []
                                }
                            else:
                                if curr_turn and curr_turn["steps"]:
                                    curr_turn["steps"][-1]["tool_result"] = tool_res_text
                        elif t == "assistant":
                            if not curr_turn:
                                curr_turn = {
                                    "turn_id": 1,
                                    "user_prompt": "(Initialization)",
                                    "user_raw": "",
                                    "timestamp": data.get("timestamp"),
                                    "steps": []
                                }
                            msg = data.get("message", {})
                            content = msg.get("content", [])
                            text_body = ""
                            tool_call = None
                            if isinstance(content, list):
                                for c in content:
                                    if isinstance(c, dict):
                                        if c.get("type") == "text":
                                            text_body += c.get("text", "")
                                        elif c.get("type") == "tool_use":
                                            tool_call = {
                                                "name": c.get("name"),
                                                "input": c.get("input", {})
                                            }
                            elif isinstance(content, str):
                                text_body = content

                            if text_body.strip() or tool_call:
                                curr_turn["steps"].append({
                                    "text": text_body.strip(),
                                    "tool_call": tool_call,
                                    "tool_result": ""
                                })

                    elif engine == "codex":
                        ptype = data.get("type")
                        payload = data.get("payload", {})
                        if ptype == "event_msg" and isinstance(payload, dict):
                            msg_type = payload.get("type")
                            if msg_type == "user_message":
                                if curr_turn:
                                    turns.append(curr_turn)
                                raw_txt = payload.get("message", "") or payload.get("text", "")
                                curr_turn = {
                                    "turn_id": len(turns) + 1,
                                    "user_prompt": clean_system_tags(raw_txt) or "(User Prompt)",
                                    "user_raw": raw_txt,
                                    "timestamp": data.get("timestamp"),
                                    "steps": []
                                }
                            elif msg_type == "agent_message":
                                if not curr_turn:
                                    curr_turn = {
                                        "turn_id": 1,
                                        "user_prompt": "(Codex Task)",
                                        "user_raw": "",
                                        "timestamp": data.get("timestamp"),
                                        "steps": []
                                    }
                                txt = payload.get("message", "") or payload.get("text", "")
                                if txt.strip():
                                    curr_turn["steps"].append({
                                        "text": txt.strip(),
                                        "tool_call": None,
                                        "tool_result": ""
                                    })
                        elif ptype == "response_item" and isinstance(payload, dict):
                            item_type = payload.get("type")
                            if item_type in ["custom_tool_call", "function_call"]:
                                if not curr_turn:
                                    curr_turn = {"turn_id": 1, "user_prompt": "(Init)", "user_raw": "", "timestamp": data.get("timestamp"), "steps": []}
                                curr_turn["steps"].append({
                                    "text": "",
                                    "tool_call": {
                                        "name": payload.get("name") or payload.get("call_id", "tool"),
                                        "input": payload.get("input") or payload.get("arguments", {})
                                    },
                                    "tool_result": ""
                                })
                            elif item_type in ["custom_tool_call_output", "function_call_output"]:
                                if curr_turn and curr_turn["steps"]:
                                    curr_turn["steps"][-1]["tool_result"] = str(payload.get("output", ""))
                except Exception:
                    continue

        if curr_turn:
            turns.append(curr_turn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    for idx, t in enumerate(turns):
        first_step_text = ""
        for st in t["steps"]:
            if st["text"]:
                first_step_text = st["text"]
                break
            elif st["tool_call"]:
                first_step_text = f"[{st['tool_call']['name']}]"
                break
        t["ai_brief"] = (first_step_text[:35] + "...") if len(first_step_text) > 35 else (first_step_text or "Done")
        t["user_brief"] = (t["user_prompt"][:30] + "...") if len(t["user_prompt"]) > 30 else t["user_prompt"]

    return {
        "engine": engine,
        "session_id": session_id,
        "file_path": file_path,
        "total_turns": len(turns),
        "turns": turns
    }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SessionHub - Claude Code & Codex Session Viewer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        dark: {
                            bg: '#090d16',
                            panel: '#0f172a',
                            card: '#161f38',
                            hover: '#1e294b',
                            border: '#1e293b',
                            accent: '#6366f1'
                        }
                    }
                }
            }
        }
    </script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        .pre-wrap { white-space: pre-wrap; word-break: break-word; }
        .swimlane-container {
            display: flex;
            align-items: center;
            height: 38px;
            overflow-x: auto;
            scroll-behavior: smooth;
        }
        .turn-capsule {
            flex-shrink: 0;
            display: flex;
            align-items: center;
            cursor: pointer;
            border-radius: 6px;
            padding: 3px 6px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }
        .turn-capsule:hover {
            transform: translateY(-2px);
        }
    </style>
</head>
<body class="h-screen flex flex-col overflow-hidden transition-colors duration-200"
    :class="isDark ? 'dark bg-[#090d16] text-slate-200' : 'bg-slate-50 text-slate-800'">
    <div id="app" class="h-full flex flex-col">
        <!-- Top Navbar -->
        <header class="border-b px-5 py-2.5 flex items-center justify-between shadow-sm transition-colors duration-200"
            :class="isDark ? 'bg-[#0f172a] border-[#1e293b]' : 'bg-white border-slate-200'">
            <div class="flex items-center space-x-3">
                <div class="bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 text-white p-2 rounded-xl shadow-md">
                    <i class="fa-solid fa-layer-group text-base"></i>
                </div>
                <div>
                    <h1 class="text-sm font-bold tracking-wide flex items-center" :class="isDark ? 'text-white' : 'text-slate-900'">
                        SessionHub
                        <span class="text-[10px] px-2 py-0.5 rounded-full ml-2 font-mono font-medium"
                            :class="isDark ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'bg-indigo-50 text-indigo-600 border border-indigo-200'">
                            Claude Code & Codex
                        </span>
                    </h1>
                    <p class="text-[11px]" :class="isDark ? 'text-slate-400' : 'text-slate-500'">Session History Viewer & Quick Resume Hub</p>
                </div>
            </div>

            <div class="flex items-center space-x-3">
                <!-- Engine Tab -->
                <div class="flex rounded-lg p-1 border"
                    :class="isDark ? 'bg-[#161f38] border-[#1e293b]' : 'bg-slate-100 border-slate-200'">
                    <button @click="setEngine('all')" :class="engine==='all' ? (isDark ? 'bg-indigo-600 text-white shadow-sm font-semibold' : 'bg-white text-indigo-600 shadow-sm font-semibold') : (isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600')" class="px-3 py-1 text-xs rounded-md transition">All</button>
                    <button @click="setEngine('claude')" :class="engine==='claude' ? (isDark ? 'bg-amber-600 text-white shadow-sm font-semibold' : 'bg-white text-amber-600 shadow-sm font-semibold') : (isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600')" class="px-3 py-1 text-xs rounded-md transition">Claude Code</button>
                    <button @click="setEngine('codex')" :class="engine==='codex' ? (isDark ? 'bg-emerald-600 text-white shadow-sm font-semibold' : 'bg-white text-emerald-600 shadow-sm font-semibold') : (isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600')" class="px-3 py-1 text-xs rounded-md transition">Codex</button>
                </div>

                <!-- Theme Toggle -->
                <button @click="toggleTheme" class="p-2 rounded-lg border text-xs transition flex items-center justify-center"
                    :class="isDark ? 'bg-[#161f38] border-[#1e293b] text-amber-400 hover:bg-[#1e294b]' : 'bg-slate-100 border-slate-200 text-slate-600 hover:bg-slate-200'"
                    :title="isDark ? 'Light mode' : 'Dark mode'">
                    <i :class="isDark ? 'fa-solid fa-sun' : 'fa-solid fa-moon'"></i>
                </button>

                <!-- Refresh -->
                <button @click="refreshAll" class="p-2 rounded-lg border text-xs transition flex items-center justify-center"
                    :class="isDark ? 'bg-[#161f38] border-[#1e293b] text-slate-400 hover:text-white' : 'bg-slate-100 border-slate-200 text-slate-600 hover:text-slate-900'"
                    title="Refresh sessions">
                    <i class="fa-solid fa-arrows-rotate" :class="{'fa-spin': loading}"></i>
                </button>
            </div>
        </header>

        <!-- Main Body -->
        <div class="flex-1 flex overflow-hidden">
            <!-- Sidebar: Project Folders -->
            <aside class="w-64 border-r flex flex-col transition-colors duration-200"
                :class="isDark ? 'bg-[#0b101d] border-[#1e293b]' : 'bg-slate-50 border-slate-200'">
                <div class="p-3 border-b flex items-center justify-between" :class="isDark ? 'border-[#1e293b]' : 'border-slate-200'">
                    <span class="text-[11px] font-bold uppercase tracking-wider flex items-center" :class="isDark ? 'text-slate-400' : 'text-slate-500'">
                        <i class="fa-regular fa-folder mr-1.5 text-indigo-400"></i> Workspaces
                    </span>
                    <span class="text-[10px] font-mono px-2 py-0.5 rounded-full"
                        :class="isDark ? 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/20' : 'bg-indigo-50 text-indigo-600'">{{ Object.keys(projects).length }}</span>
                </div>
                <div class="flex-1 overflow-y-auto p-2 space-y-1">
                    <button @click="selectProject('')"
                        :class="!selectedProject ? (isDark ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40 shadow-sm font-semibold' : 'bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm font-semibold') : (isDark ? 'text-slate-400 hover:bg-[#161f38] hover:text-slate-200 border-transparent' : 'text-slate-600 hover:bg-slate-100 border-transparent')"
                        class="w-full text-left px-3 py-2 rounded-xl text-xs border flex items-center justify-between transition">
                        <span class="truncate"><i class="fa-solid fa-globe mr-2 text-indigo-400"></i>All Projects</span>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-mono" :class="isDark ? 'bg-[#161f38] text-slate-400' : 'bg-slate-200 text-slate-600'">{{ totalSessions }}</span>
                    </button>
                    <button v-for="(count, p) in projects" :key="p" @click="selectProject(p)"
                        :class="selectedProject===p ? (isDark ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40 shadow-sm font-semibold' : 'bg-indigo-50 text-indigo-700 border-indigo-200 shadow-sm font-semibold') : (isDark ? 'text-slate-400 hover:bg-[#161f38] hover:text-slate-200 border-transparent' : 'text-slate-600 hover:bg-slate-100 border-transparent')"
                        class="w-full text-left px-3 py-2 rounded-xl text-xs border flex items-center justify-between transition group">
                        <span class="truncate" :title="p">
                            <i class="fa-regular fa-folder-open mr-2 text-slate-500 group-hover:text-indigo-400"></i>{{ p }}
                        </span>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-mono" :class="isDark ? 'bg-[#161f38] text-slate-400' : 'bg-slate-200 text-slate-600'">{{ count }}</span>
                    </button>
                </div>
            </aside>

            <!-- Center: Session Cards List -->
            <section class="w-80 border-r flex flex-col transition-colors duration-200"
                :class="isDark ? 'bg-[#0f172a]/50 border-[#1e293b]' : 'bg-slate-50/50 border-slate-200'">
                <div class="p-3 border-b space-y-2" :class="isDark ? 'border-[#1e293b]' : 'border-slate-200'">
                    <div class="relative">
                        <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-500"></i>
                        <input v-model="searchQuery" @keyup.enter="doSearch" type="text" placeholder="Search prompt / id / branch..."
                            class="w-full rounded-xl pl-8 pr-7 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 border transition"
                            :class="isDark ? 'bg-[#161f38] border-[#1e293b] text-slate-200 placeholder-slate-500' : 'bg-white border-slate-300 text-slate-800 placeholder-slate-400'">
                        <button v-if="searchQuery" @click="searchQuery=''; fetchSessions()" class="absolute right-2.5 top-2 text-xs text-slate-400 hover:text-slate-200">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    </div>
                    <div class="flex items-center justify-between text-[11px] px-1" :class="isDark ? 'text-slate-400' : 'text-slate-500'">
                        <span>{{ sessions.length }} sessions</span>
                        <button @click="doFullSearch" class="text-indigo-400 hover:text-indigo-300 font-medium hover:underline flex items-center text-[11px]">
                            <i class="fa-solid fa-bolt mr-1"></i> Full-text Search
                        </button>
                    </div>
                </div>

                <div class="flex-1 overflow-y-auto p-2 space-y-2">
                    <div v-if="loading" class="text-center py-10 text-slate-500 text-xs">
                        <i class="fa-solid fa-spinner fa-spin mr-1"></i> Loading...
                    </div>
                    <div v-else-if="sessions.length === 0" class="text-center py-12 text-slate-500 text-xs">
                        No sessions found
                    </div>
                    <div v-for="s in sessions" :key="s.id" @click="loadDetail(s)"
                        :class="currentSession && currentSession.id === s.id ? (isDark ? 'bg-[#161f38] border-indigo-500 shadow-md ring-1 ring-indigo-500/40' : 'bg-white border-indigo-500 shadow-md ring-1 ring-indigo-500/30') : (isDark ? 'bg-[#121a2f] hover:bg-[#161f38] border-[#1e293b]' : 'bg-white hover:bg-slate-50 border-slate-200')"
                        class="border p-3 rounded-xl cursor-pointer transition flex flex-col space-y-2">
                        <div class="flex items-center justify-between">
                            <span :class="s.engine === 'claude' ? (isDark ? 'bg-amber-500/10 text-amber-300 border-amber-500/30' : 'bg-amber-50 text-amber-700 border-amber-200') : (isDark ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-emerald-50 text-emerald-700 border-emerald-200')"
                                class="px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase tracking-wider font-mono">
                                {{ s.engine }}
                            </span>
                            <span class="text-[10px] text-slate-400 font-mono"><i class="fa-regular fa-clock mr-1"></i>{{ s.time_str }}</span>
                        </div>
                        <p class="text-xs line-clamp-2 leading-relaxed font-normal" :class="isDark ? 'text-slate-200' : 'text-slate-700'">
                            {{ s.summary }}
                        </p>
                        <div v-if="s.match_snippet" class="text-[10px] p-2 rounded-lg border line-clamp-2 font-mono"
                            :class="isDark ? 'bg-amber-950/20 text-amber-200 border-amber-500/30' : 'bg-amber-50 text-amber-800 border-amber-200'">
                            Matched: {{ s.match_snippet }}
                        </div>
                        <div class="flex items-center justify-between text-[10px] pt-1.5 border-t" :class="isDark ? 'text-slate-400 border-[#1e293b]' : 'text-slate-500 border-slate-100'">
                            <span class="truncate max-w-[140px]" :title="s.project">
                                <i class="fa-regular fa-folder mr-1 text-slate-500"></i>{{ s.project_name }}
                            </span>
                            <span class="font-mono">{{ s.msg_count }} turns · {{ s.size_kb }} KB</span>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Right: Detail & Turns View -->
            <main class="flex-1 flex flex-col overflow-hidden transition-colors duration-200"
                :class="isDark ? 'bg-[#090d16]' : 'bg-slate-100/50'">
                <div v-if="!currentSession" class="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-3">
                    <div class="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl border shadow-sm"
                        :class="isDark ? 'bg-[#0f172a] border-[#1e293b]' : 'bg-white border-slate-200'">
                        <i class="fa-regular fa-comments text-indigo-400"></i>
                    </div>
                    <p class="text-xs text-slate-400">Select a session from the list to view full dialogue flow and resume command</p>
                </div>

                <div v-else class="h-full flex flex-col">
                    <!-- Session Detail Header -->
                    <div class="px-5 py-3 border-b flex items-center justify-between transition-colors duration-200"
                        :class="isDark ? 'bg-[#0f172a] border-[#1e293b]' : 'bg-white border-slate-200'">
                        <div class="space-y-1">
                            <div class="flex items-center space-x-2">
                                <span :class="currentSession.engine === 'claude' ? (isDark ? 'bg-amber-500/10 text-amber-300 border-amber-500/30' : 'bg-amber-100 text-amber-800 border-amber-300') : (isDark ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-emerald-100 text-emerald-800 border-emerald-300')"
                                    class="px-2 py-0.5 rounded-full text-xs font-bold border uppercase font-mono">
                                    {{ currentSession.engine }}
                                </span>
                                <h2 class="text-xs font-bold font-mono" :class="isDark ? 'text-slate-200' : 'text-slate-800'">{{ currentSession.id }}</h2>
                                <span v-if="currentSession.git_branch" class="text-[11px] px-2 py-0.5 rounded-full border"
                                    :class="isDark ? 'bg-[#161f38] text-slate-300 border-[#1e293b]' : 'bg-slate-100 text-slate-600 border-slate-200'">
                                    <i class="fa-solid fa-code-branch mr-1 text-indigo-400"></i>{{ currentSession.git_branch }}
                                </span>
                            </div>
                            <div class="text-[11px] flex items-center space-x-3" :class="isDark ? 'text-slate-400' : 'text-slate-500'">
                                <span><i class="fa-regular fa-folder mr-1 text-indigo-400"></i>Path: <span class="font-mono font-medium">{{ currentSession.project }}</span></span>
                                <span><i class="fa-regular fa-clock mr-1"></i>{{ currentSession.time_str }}</span>
                            </div>
                        </div>

                        <!-- Copy Button -->
                        <div class="flex items-center space-x-2">
                            <button @click="copyCommand(currentSession.resume_cmd)"
                                class="bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-1.5 rounded-xl text-xs font-medium flex items-center shadow transition">
                                <i class="fa-regular fa-copy mr-1.5"></i> Copy Resume Command
                            </button>
                        </div>
                    </div>

                    <!-- Swimlane Navigation -->
                    <div v-if="turns.length > 0" class="border-b px-5 py-2.5 flex flex-col space-y-2 transition-colors duration-200"
                        :class="isDark ? 'bg-[#0f172a] border-[#1e293b]' : 'bg-white border-slate-200'">
                        <div class="flex items-center justify-between text-[11px]">
                            <div class="flex items-center space-x-2">
                                <span class="font-bold text-xs flex items-center" :class="isDark ? 'text-slate-200' : 'text-slate-700'">
                                    <i class="fa-solid fa-timeline mr-1.5 text-indigo-400"></i>Turn Swimlane
                                </span>
                                <span class="text-slate-400 text-[10px]">（{{ turns.length }} turns, click capsule to jump）</span>
                            </div>
                            <div class="flex items-center space-x-1.5">
                                <button @click="prevTurn" :disabled="activeTurnIndex <= 0"
                                    class="px-2.5 py-1 rounded-lg text-[11px] border disabled:opacity-30 disabled:cursor-not-allowed transition flex items-center"
                                    :class="isDark ? 'bg-[#161f38] border-[#1e293b] hover:bg-[#1e294b] text-slate-200' : 'bg-slate-100 border-slate-200 hover:bg-slate-200 text-slate-700'">
                                    <i class="fa-solid fa-chevron-left mr-1"></i>Prev (P)
                                </button>
                                <span class="text-[11px] font-mono px-2 font-semibold" :class="isDark ? 'text-indigo-400' : 'text-indigo-600'">
                                    {{ activeTurnIndex + 1 }} / {{ turns.length }}
                                </span>
                                <button @click="nextTurn" :disabled="activeTurnIndex >= turns.length - 1"
                                    class="px-2.5 py-1 rounded-lg text-[11px] border disabled:opacity-30 disabled:cursor-not-allowed transition flex items-center"
                                    :class="isDark ? 'bg-[#161f38] border-[#1e293b] hover:bg-[#1e294b] text-slate-200' : 'bg-slate-100 border-slate-200 hover:bg-slate-200 text-slate-700'">
                                    Next (N)<i class="fa-solid fa-chevron-right ml-1"></i>
                                </button>
                            </div>
                        </div>

                        <!-- Capsules -->
                        <div class="swimlane-container rounded-xl p-1 border flex items-center space-x-1.5"
                            :class="isDark ? 'bg-[#090d16] border-[#1e293b]' : 'bg-slate-100 border-slate-200'">
                            <div v-for="(turn, idx) in turns" :key="idx"
                                @click="jumpToTurn(idx)"
                                :title="`Turn #${idx+1}:\n[User] ${turn.user_prompt}\n[AI] ${turn.ai_brief}`"
                                :class="[
                                    activeTurnIndex === idx
                                        ? (isDark ? 'bg-indigo-600/30 border-indigo-500 shadow ring-1 ring-indigo-500' : 'bg-indigo-100 border-indigo-400 ring-1 ring-indigo-400')
                                        : (isDark ? 'bg-[#161f38] hover:bg-[#1e294b] border-[#1e293b]' : 'bg-white hover:bg-slate-50 border-slate-200')
                                ]"
                                class="turn-capsule border space-x-1.5 text-[10px]">
                                <span class="font-mono font-bold" :class="isDark ? 'text-slate-400' : 'text-slate-500'">#{{ idx+1 }}</span>
                                <span class="w-2 h-2 rounded-full bg-amber-400" title="User Prompt"></span>
                                <span class="w-2 h-2 rounded-full bg-indigo-400" :title="`Model execution: ${turn.steps.length} steps`"></span>
                                <span class="text-[9px] font-mono text-slate-400">({{ turn.steps.length }})</span>
                            </div>
                        </div>
                    </div>

                    <!-- Quick Resume Banner -->
                    <div class="border-b px-5 py-2 flex items-center justify-between text-xs transition-colors duration-200"
                        :class="isDark ? 'bg-[#0b101d] border-[#1e293b]' : 'bg-slate-50 border-slate-200'">
                        <div class="flex items-center space-x-2 font-mono text-[11px] truncate" :class="isDark ? 'text-indigo-300' : 'text-indigo-700'">
                            <span class="text-slate-500">$</span>
                            <span>cd {{ currentSession.project }} && {{ currentSession.resume_cmd }}</span>
                        </div>
                        <button @click="copyCommand('cd ' + currentSession.project + ' && ' + currentSession.resume_cmd)"
                            class="text-slate-400 hover:text-indigo-400 ml-2 text-xs" title="Copy full command">
                            <i class="fa-regular fa-copy"></i>
                        </button>
                    </div>

                    <!-- Turns & Messages Stream -->
                    <div id="turns-container" class="flex-1 overflow-y-auto p-5 space-y-6">
                        <div v-if="detailLoading" class="text-center py-12 text-slate-400 text-xs">
                            <i class="fa-solid fa-spinner fa-spin mr-1"></i> Loading conversation...
                        </div>
                        <div v-else-if="turns.length === 0" class="text-center py-12 text-slate-400 text-xs">
                            No readable messages
                        </div>

                        <!-- Turn Card -->
                        <div v-for="(turn, idx) in turns" :key="idx" :id="'turn-' + idx"
                            :class="activeTurnIndex === idx ? (isDark ? 'ring-1 ring-indigo-500 bg-[#121a2f]' : 'ring-1 ring-indigo-400 bg-white') : (isDark ? 'bg-[#0f172a] border-[#1e293b]' : 'bg-white border-slate-200')"
                            class="border rounded-2xl p-4 space-y-4 shadow-sm transition duration-200">

                            <!-- Turn Header -->
                            <div class="flex items-center justify-between border-b pb-2.5" :class="isDark ? 'border-[#1e293b]' : 'border-slate-100'">
                                <div class="flex items-center space-x-2">
                                    <span class="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold"
                                        :class="isDark ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : 'bg-indigo-50 text-indigo-700 border border-indigo-200'">
                                        Turn #{{ idx + 1 }}
                                    </span>
                                    <span class="text-[11px] text-slate-400">{{ turn.steps.length }} execution steps</span>
                                </div>
                                <span v-if="turn.timestamp" class="text-[11px] font-mono text-slate-400">{{ turn.timestamp }}</span>
                            </div>

                            <!-- 1. User Prompt -->
                            <div class="space-y-1.5">
                                <div class="flex items-center space-x-2 text-xs font-bold text-amber-400">
                                    <i class="fa-solid fa-user-circle text-sm"></i>
                                    <span>User Prompt</span>
                                </div>
                                <div class="p-3.5 rounded-xl border text-xs leading-relaxed pre-wrap font-mono"
                                    :class="isDark ? 'bg-[#161f38] border-[#1e293b] text-slate-100' : 'bg-amber-50/70 border-amber-200 text-slate-800'">
                                    {{ turn.user_prompt }}
                                </div>
                            </div>

                            <!-- 2. Assistant Steps -->
                            <div class="space-y-2.5">
                                <div class="flex items-center space-x-2 text-xs font-bold text-indigo-400">
                                    <i class="fa-solid fa-robot text-sm"></i>
                                    <span>Assistant & Tools</span>
                                </div>

                                <div v-if="turn.steps.length === 0" class="text-xs text-slate-500 italic px-2">
                                    (No output in this turn)
                                </div>

                                <div v-for="(step, sidx) in turn.steps" :key="sidx" class="space-y-1.5 pl-2 border-l-2"
                                    :class="isDark ? 'border-indigo-900/60' : 'border-indigo-200'">

                                    <div v-if="step.text" class="p-3.5 rounded-xl border text-xs leading-relaxed pre-wrap font-mono"
                                        :class="isDark ? 'bg-[#161f38]/60 border-[#1e293b] text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-700'">
                                        {{ step.text }}
                                    </div>

                                    <div v-if="step.tool_call" class="p-3 rounded-xl border text-[11px] font-mono space-y-1.5"
                                        :class="isDark ? 'bg-[#090d16] border-[#1e293b] text-indigo-300' : 'bg-indigo-50/60 border-indigo-200 text-indigo-800'">
                                        <div class="flex items-center space-x-2 font-bold">
                                            <i class="fa-solid fa-terminal text-indigo-400"></i>
                                            <span>Tool Call: {{ step.tool_call.name }}</span>
                                        </div>
                                        <div class="text-[10px] overflow-x-auto max-h-36 opacity-85">
                                            <pre>{{ JSON.stringify(step.tool_call.input, null, 2) }}</pre>
                                        </div>
                                    </div>

                                    <div v-if="step.tool_result" class="p-3 rounded-xl border text-[11px] font-mono space-y-1.5"
                                        :class="isDark ? 'bg-[#090d16]/70 border-[#1e293b] text-slate-400' : 'bg-slate-100 border-slate-200 text-slate-600'">
                                        <div class="flex items-center space-x-2 font-bold">
                                            <i class="fa-solid fa-arrow-turn-down text-slate-400"></i>
                                            <span>Tool Result Output</span>
                                        </div>
                                        <div class="text-[10px] overflow-x-auto max-h-40 pre-wrap">
                                            {{ step.tool_result }}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>

        <!-- Toast -->
        <div v-if="toastMsg" class="fixed bottom-6 right-6 bg-indigo-600 text-white px-4 py-2.5 rounded-xl text-xs shadow-2xl flex items-center space-x-2 z-50 animate-bounce">
            <i class="fa-solid fa-check"></i>
            <span>{{ toastMsg }}</span>
        </div>
    </div>

    <script>
        const { createApp } = Vue;
        createApp({
            data() {
                return {
                    isDark: localStorage.getItem('theme') !== 'light',
                    engine: 'all',
                    selectedProject: '',
                    searchQuery: '',
                    sessions: [],
                    projects: {},
                    totalSessions: 0,
                    loading: false,
                    detailLoading: false,
                    currentSession: null,
                    turns: [],
                    activeTurnIndex: 0,
                    toastMsg: ''
                };
            },
            mounted() {
                this.fetchSessions();
                window.addEventListener('keydown', this.handleKeydown);
            },
            beforeUnmount() {
                window.removeEventListener('keydown', this.handleKeydown);
            },
            methods: {
                toggleTheme() {
                    this.isDark = !this.isDark;
                    localStorage.setItem('theme', this.isDark ? 'dark' : 'light');
                },
                async fetchSessions() {
                    this.loading = true;
                    try {
                        let url = `/api/sessions?engine=${this.engine}`;
                        if (this.selectedProject) url += `&project=${encodeURIComponent(this.selectedProject)}`;
                        if (this.searchQuery) url += `&q=${encodeURIComponent(this.searchQuery)}`;
                        const res = await fetch(url);
                        const data = await res.json();
                        this.sessions = data.sessions;
                        this.projects = data.projects;
                        this.totalSessions = data.total;
                    } catch (e) {
                        this.showToast('Failed to load sessions');
                    } finally {
                        this.loading = false;
                    }
                },
                setEngine(eng) {
                    this.engine = eng;
                    this.fetchSessions();
                },
                selectProject(p) {
                    this.selectedProject = p;
                    this.fetchSessions();
                },
                doSearch() {
                    this.fetchSessions();
                },
                async doFullSearch() {
                    if (!this.searchQuery || this.searchQuery.length < 2) {
                        this.showToast('Please input at least 2 characters');
                        return;
                    }
                    this.loading = true;
                    try {
                        const res = await fetch(`/api/search_full?q=${encodeURIComponent(this.searchQuery)}&engine=${this.engine}`);
                        const data = await res.json();
                        this.sessions = data.sessions;
                        this.showToast(`Found ${data.total} records`);
                    } catch (e) {
                        this.showToast('Search failed');
                    } finally {
                        this.loading = false;
                    }
                },
                refreshAll() {
                    this.fetchSessions();
                    if (this.currentSession) {
                        this.loadDetail(this.currentSession);
                    }
                },
                async loadDetail(session) {
                    this.currentSession = session;
                    this.detailLoading = true;
                    this.turns = [];
                    this.activeTurnIndex = 0;
                    try {
                        const res = await fetch(`/api/session/${session.engine}/${session.id}`);
                        const data = await res.json();
                        this.turns = data.turns;
                    } catch (e) {
                        this.showToast('Failed to load session details');
                    } finally {
                        this.detailLoading = false;
                    }
                },
                jumpToTurn(index) {
                    if (index < 0 || index >= this.turns.length) return;
                    this.activeTurnIndex = index;
                    const el = document.getElementById('turn-' + index);
                    if (el) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                },
                prevTurn() {
                    if (this.activeTurnIndex > 0) {
                        this.jumpToTurn(this.activeTurnIndex - 1);
                    }
                },
                nextTurn() {
                    if (this.activeTurnIndex < this.turns.length - 1) {
                        this.jumpToTurn(this.activeTurnIndex + 1);
                    }
                },
                handleKeydown(e) {
                    if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
                    if (e.key === 'p' || e.key === 'P' || e.key === 'ArrowUp') {
                        this.prevTurn();
                    } else if (e.key === 'n' || e.key === 'N' || e.key === 'ArrowDown') {
                        this.nextTurn();
                    }
                },
                copyCommand(cmd) {
                    if (!cmd) return;
                    if (navigator.clipboard && window.isSecureContext) {
                        navigator.clipboard.writeText(cmd).then(() => {
                            this.showToast('Resume command copied!');
                        }).catch(() => {
                            this.fallbackCopy(cmd);
                        });
                    } else {
                        this.fallbackCopy(cmd);
                    }
                },
                fallbackCopy(text) {
                    const textArea = document.createElement("textarea");
                    textArea.value = text;
                    textArea.style.position = "fixed";
                    textArea.style.left = "-999999px";
                    textArea.style.top = "-999999px";
                    document.body.appendChild(textArea);
                    textArea.focus();
                    textArea.select();
                    try {
                        document.execCommand('copy');
                        this.showToast('Resume command copied!');
                    } catch (err) {
                        this.showToast('Copy failed');
                    }
                    textArea.remove();
                },
                showToast(msg) {
                    this.toastMsg = msg;
                    setTimeout(() => { this.toastMsg = ''; }, 2500);
                }
            }
        }).mount('#app');
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_TEMPLATE

if __name__ == "__main__":
    port = int(os.getenv("PORT", 20089))
    uvicorn.run(app, host="0.0.0.0", port=port)
