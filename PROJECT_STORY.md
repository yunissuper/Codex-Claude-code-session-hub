# Codex-Claude-code-session-hub 项目深度解析与故事背景 (供 Hermes Agent / 推文编写参考)

---

## 📌 一、 项目定位与一句话 Slogan
- **项目全称**：Codex-Claude-code-session-hub
- **一句话 Slogan**：给 Claude Code 与 OpenAI Codex CLI 打造的可视化“时空胶囊”与工作区管理器。
- **核心价值**：告别 CLI 盲盒式恢复与上下文割裂，实现基于真实工作区（Workspace）聚合、DeepSeek Harness 级多维泳道导航、全文深度检索与无缝一键恢复。

---

## 🎯 二、 痛点与开发背景（为什么做这个项目？）

### 1. CLI 原生 `/resume` 的“盲盒之痛”
- **痛点**：使用 Claude Code 或 Codex CLI 进行深度工程开发时，会话动辄数百轮。但官方 CLI 的 `/resume` 只展示单行截断的模糊摘要（且常常只截取到系统的 tool_result 或第一句提示词），隔天或多天后根本无法分辨哪个会话对应哪部分代码逻辑。
- **误恢复代价**：频繁误进旧会话导致上下文被无关历史污染，浪费大量 Token，甚至引入错误的脏代码状态。

### 2. “散落各地的哈希文件夹”与“项目工作区缺失”
- **痛点**：Claude Code 将会话根据路径转义（如 `-home-yls-project`）或哈希分散在 `~/.claude/projects/`，Codex 会话则散落在 `~/.codex/sessions/`。开发者无法以**“当前项目/代码仓库”**的全局视角总览该项目所有历史迭代分支和 Agent 思考历程。

### 3. Agent 过程不可见与信息淹没
- **痛点**：CLI 终端在执行多步 Tool（Bash、Edit、Grep）时滚动极快，历史对话与工具执行结果交织。开发者很难快速定位“第 3 轮交互中模型到底改了哪几个文件”、“第 5 轮报错信息是什么”。

---

## 🚀 三、 核心功能与技术亮点

### 1. 📂 真实工作区聚合 (Workspace-Aware Grouping)
- **智能路径反解析**：自动解析 Claude Code 与 Codex 的散落日志，根据真实工程目录（Project Path）建立工作区索引，告别无意义的哈希串。
- **全生命周期元数据**：展示每个会话的关联分支（Git Branch）、最后活跃时间、总交互轮次（Turns）与累计工具调用步数（Steps）。

### 2. ⚡ DeepSeek Harness 风格的交互式“时空泳道” (Turn-based Swimlane)
- **胶囊化时间轴**：将冗长的会话结构化为离散的对话胶囊（User 🟡 + AI 🟣 + Tool Calls 计数）。
- **极速跳转与快捷键**：支持点击顶部泳道胶囊平滑滚动定位，并深度适配键盘快捷键（`P` 键跳转上一轮，`N` 键跳转下一轮，方向键导航），极客体验拉满。

### 3. 🔍 多维毫秒级检索与全文穿透 (Deep Full-Text Search)
- **双层搜索体系**：
  - **表层过滤**：按 Prompt 关键词、Session ID、Git 分支即时过滤。
  - **深层穿透**：全文扫描 JSONL 底层原始记录，穿透搜索 Tool 调用入参、命令执行返回日志、历史报错及模型内部思考。

### 4. 🛠️ 结构化 Agent 行为透视 (Structured Inspection)
- **智能分离降噪**：精准区分系统级合成的 `tool_result` 与用户真正输入的 Prompt，消除数据冗余。
- **模型回答完整呈现**：不仅保留最终结论，还能逐步展开查看工具调用代码块与终端执行回显。

### 5. 📋 跨网络一键接管命令生成 (One-Click CLI Resumption)
- **开箱即用**：自动生成形如 `cd /path/to/project && claude --resume <session_id>` 或 `codex resume <session_id>`。
- **HTTP/反代剪贴板兼容**：内置 `execCommand` 降级兼容机制，在无 HTTPS 或 FRP 反向代理内网环境下依然能一键复制到剪贴板。

### 6. 🌓 极客美学与零构建自包含架构
- **午夜暗黑与极简明亮双主题**：基于 `#090d16` Midnight 极客配色，支持本地偏好记忆。
- **零 Node.js 编译构建负担**：纯 FastAPI 后端 + 单文件自包含响应式前端（Vue 3 + TailwindCSS CDN），`pip install` 即可在任何服务器、容器或开发机秒级启动。

---

## 🏗️ 四、 架构设计与技术栈

- **后端引擎**：Python 3 + FastAPI + Uvicorn（极轻量、高并发异步流式解析）
- **数据流**：原生流式读取 `~/.claude/projects/**/*.jsonl` 与 `~/.codex/sessions/**/*.jsonl`
- **前端栈**：Vue 3 响应式系统 + TailwindCSS + FontAwesome 图标库
- **部署方式**：单入口 `python3 app.py`，支持环境变量自定义端口与数据目录

---

## 📢 五、 微信公众号/自媒体推文创作素材建议（Hermes 提取点）

1. **爆款标题方向**：
   - 《受够了 Claude Code /resume 的单行摘要？我给它写了个可视化工作区面板》
   - 《告别 CLI 盲盒！给 Claude Code 和 Codex 装上“时空泳道”与全文检索》
   - 《深度开发者的刚需：如何像看电影一样回放 Agent 的每一步代码修改？》

2. **核心传播金句**：
   - *“Agent 替我们写代码，谁来替我们记住 Agent 思考过的每一个瞬间？”*
   - *“不要把时间浪费在猜 ‘哪个 session 是我昨天改完 bug 的那个’ 上。”*
   - *“不仅是历史记录器，更是多项目并发开发的 Agent 驾驶舱。”*

3. **视觉/排版建议**：
   - 重点截取：**顶部 Harness 风格彩色泳道图**、**深色/浅色主题对比图**、**全文检索高亮图**、**结构化展开 Tool 调用卡片图**。
