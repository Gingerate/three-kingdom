"""Wiki 生成模块 —— 从知识摘要 distill 出结构化 Wiki 页面"""

from __future__ import annotations

import json
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.core.database import (
    get_knowledge_summaries,
    save_wiki_page,
    get_wiki_pages,
    get_wiki_page,
)


DISTILL_PROMPT = """你是一个知识编纂专家。将以下多条知识摘要编纂成一篇结构化的 Wiki 页面。

## 要求
1. 标题简洁有力，概括主题
2. 内容按逻辑结构组织（背景、经过、影响、相关人物等）
3. 保留所有有价值的知识点，不要遗漏
4. 使用 markdown 格式，层次清晰
5. 语言庄重典雅，符合历史叙事风格
6. 在文末标注主要参考来源

## 输出格式（纯 markdown）
# 标题

## 一、小节名
内容...

## 二、小节名
内容...

---
**参考来源**：...

## 知识摘要列表
{summaries}

## 主题提示
{topic_hint}

请开始编纂："""


TOPIC_DETECT_PROMPT = """分析以下知识摘要，给出一个主题标签。

可选主题：人物、战役、政治、制度、地理、文化、综合

只输出主题标签，不要其他内容。

摘要：
{summaries}"""


def detect_topic(summaries: list[dict]) -> str:
    """检测摘要的主题"""
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.1,
        max_tokens=32,
    )

    text = "\n".join(f"- {s['summary']}" for s in summaries[:20])

    try:
        response = llm.invoke([
            SystemMessage(content=TOPIC_DETECT_PROMPT.format(summaries=text)),
            HumanMessage(content="请判断主题"),
        ])
        topic = response.content.strip()
        # 验证是否是合法主题
        valid_topics = {"人物", "战役", "政治", "制度", "地理", "文化", "综合"}
        return topic if topic in valid_topics else "综合"
    except Exception:
        return "综合"


def generate_wiki(summaries: list[dict], topic_hint: str = "") -> tuple[str, str]:
    """从摘要生成 Wiki 页面，返回 (title, content)"""
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.3,
        max_tokens=4096,
    )

    summaries_text = "\n".join(
        f"- [{s.get('created_at', '')}] 问：{s['question']}\n  答摘要：{s['summary']}"
        for s in summaries
    )

    if not topic_hint:
        topic_hint = detect_topic(summaries)

    response = llm.invoke([
        SystemMessage(content=DISTILL_PROMPT.format(
            summaries=summaries_text,
            topic_hint=topic_hint or "综合",
        )),
        HumanMessage(content="请编纂 Wiki 页面"),
    ])

    content = response.content.strip()

    # 从内容中提取标题
    title = "知识摘要"
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return title, content


def distill_and_save(session_ids: list[str] | None = None,
                     topic: str = "") -> dict:
    """从指定会话（或最近的摘要）distill 出 Wiki 页面"""
    # 获取摘要
    summaries = []
    if session_ids:
        for sid in session_ids:
            summaries.extend(get_knowledge_summaries(session_id=sid))
    else:
        summaries = get_knowledge_summaries(limit=50)

    if not summaries:
        return {"status": "error", "message": "没有可用的知识摘要"}

    # 如果没有指定主题，先检测（避免 generate_wiki 内部再检测一次）
    if not topic:
        topic = detect_topic(summaries)

    # 生成 Wiki
    title, content = generate_wiki(summaries, topic_hint=topic)

    # 保存
    source_sessions = list(set(s["session_id"] for s in summaries))
    save_wiki_page(
        title=title,
        content=content,
        topic=topic,
        source_sessions=source_sessions,
    )

    return {
        "status": "ok",
        "title": title,
        "content": content,
        "summary_count": len(summaries),
    }
