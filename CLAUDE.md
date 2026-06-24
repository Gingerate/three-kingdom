# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

三国历史知识库（公元 184-280 年），基于 Agentic RAG + 知识图谱的智能问答系统。

## 常用命令

### 包管理（严格使用 uv）

```bash
uv pip install <package>      # 安装依赖
uv pip uninstall <package>    # 卸载依赖
uv lock                       # 锁定依赖
uv run python <script>        # 运行脚本
```

### 后端

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000   # 启动开发服务器
python scripts/ingest_qinhan.py                      # 运行入库脚本
```

### 前端

```bash
cd frontend
npm install        # 安装依赖
npm run dev        # 启动开发服务器 (端口 5174)
npm run build      # 构建生产版本
npx tsc --noEmit   # TypeScript 类型检查
```

## 架构概览

### 后端 (FastAPI)

**请求流向：**
```
API Router → RAG Agent (LangGraph) → VectorStore (Chroma) + LLM
                ↓
         Memory (自动摘要) → SQLite + Chroma (qa_memory)
```

**核心模块：**

- `app/rag/agent.py` — LangGraph 六节点状态机：router → decompose → retrieve → grade → generate → reflect
- `app/rag/vectorstore.py` — ChromaDB 封装，支持多 collection（默认 + qa_memory）
- `app/rag/memory.py` — 对话记忆：存储 → LLM 提取摘要 → 入向量库
- `app/rag/wiki.py` — Wiki 蒸馏：多条摘要 → LLM 生成结构化 markdown
- `app/kg/pipeline.py` — 入库管线：加载文档 → 切分 → embedding → Chroma
- `app/kg/text_splitter.py` — 两级切分：章节粗切 → 段落细切（滑动窗口）
- `app/core/progress.py` — 全局进度追踪器，支持 SSE 订阅
- `app/prompts/` — 三层提示词系统（identity.md / rules.md），修改 .md 文件不改代码

**配置：** `app/core/config.py` 从 `.env` 读取，使用 pydantic-settings

### 前端 (React + TypeScript)

**页面路由：**
- `/chat` — 智能问答（流式 SSE）
- `/wiki` — 知识沉淀（卷轴式阅读器，IntersectionObserver 逐段动画）
- `/graph` — 知识图谱（G6 力导向图）
- `/data` — 数据管理（上传、入库、SSE 实时进度）

**设计风格：** 水墨史诗主题，详见 `index.css`
- 色彩：宣纸 `#f7f3ec` / 朱砂 `#b94432` / 青石 `#5c7a6e` / 墨黑 `#1a1a1a`
- 字体：LXGW WenKai（霞鹜文楷）
- 特效：胶片颗粒、暗角、漂浮粒子、水墨山峦视差

### 数据存储

- `backend/data/raw/` — 已转换的 .md 文件（带 YAML frontmatter，入库流程读取此目录）
- `backend/data/originals/` — 原始文献（上传时自动移入，保留原始格式）
- `backend/data/chroma/` — ChromaDB 向量数据库
- `backend/data/sqlite.db` — 知识图谱 + 对话记录 + 知识摘要 + Wiki 页面

## 信源分级

回答必须标注来源等级：
- 一级：正史（三国志、后汉书等）→ "据《三国志·XX传》记载..."
- 二级：演义（三国演义）→ "在《三国演义》中...（此为文学创作）"
- 三级：野史（世说新语等）→ "据野史记载...（可信度存疑）"

## 开发约定

- **Embedding 模型**：`dunzhang/stella-mrl-large-zh-v3.5-1792d`，本地 HuggingFace，MRL 降维至 1024d
- **LLM**：通过 OpenAI 兼容 API 调用，模型 ID 在 `.env` 中配置
- **进度条**：使用 `InkProgress` 组件（水墨风格），不要用 Ant Design 默认 Progress
- **提示词修改**：编辑 `backend/app/prompts/*.md` 文件，无需改代码
- **上传流程**：`POST /api/ingest/upload` 完整流程：格式检查 → 图片PDF检测 → 转换为.md（带YAML frontmatter）→ 质量门禁 → 保存到 raw/ → 原始文件移到 originals/
- **入库流程**：`POST /api/ingest` 返回 task_id，前端通过 `GET /api/ingest/progress/{task_id}` SSE 监听实时进度（只读取 raw/ 下的 .md/.txt 文件）
- **计划文件**：在哪个项目中讨论计划，就在哪个项目目录中保存计划文件（`.planning/` 目录）
- **Memory 文件**：每个项目的 memory 存储在项目目录下的 `.memory/` 目录中，按项目隔离
