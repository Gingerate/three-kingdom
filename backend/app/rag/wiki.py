"""Wiki 生成模块 —— 从知识摘要 distill 出结构化 Wiki 页面"""

from __future__ import annotations

import json
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

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


TOPIC_CLUSTER_PROMPT = """分析以下知识摘要，按主题进行聚类分组。

## 要求
1. 根据摘要内容的关联性，自然地归纳出主题分类
2. 主题应该能概括该组摘要的核心内容
3. 主题名称简洁（2-6个字），如：赤壁之战、诸葛亮北伐、曹魏政权、蜀汉内政等
4. 每条摘要只归入一个最相关的主题
5. 输出 JSON 格式

## 输出格式
{
  "clusters": {
    "主题1": [0, 2, 5],
    "主题2": [1, 3],
    "主题3": [4, 6, 7]
  }
}

其中数字是摘要的索引（从0开始）。

## 知识摘要列表
{summaries}

请开始聚类："""


def cluster_by_topic(summaries: list[dict]) -> dict[str, list[int]]:
    """将摘要按主题聚类，返回 {主题: [摘要索引列表]}"""
    from app.rag.agent import get_llm
    llm = get_llm(temperature=0.2)

    summaries_text = "\n".join(
        f"[{i}] {s['summary']}"
        for i, s in enumerate(summaries[:30])  # 限制30条避免太长
    )

    try:
        # 使用 replace 而非 format，避免 JSON 示例中的花括号被误解析
        prompt = TOPIC_CLUSTER_PROMPT.replace("{summaries}", summaries_text)
        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="请进行主题聚类"),
        ])

        # 解析 JSON
        from app.utils.parsers import parse_llm_json
        data = parse_llm_json(response.content)

        if not data or "clusters" not in data:
            # 聚类失败，全部归为"综合"
            return {"综合": list(range(len(summaries)))}

        clusters = data["clusters"]

        # 验证和清理
        valid_clusters = {}
        all_indices = set(range(len(summaries)))
        covered_indices = set()

        for topic, indices in clusters.items():
            if not isinstance(indices, list):
                continue
            # 只保留有效的索引
            valid_indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(summaries)]
            if valid_indices:
                valid_clusters[topic] = valid_indices
                covered_indices.update(valid_indices)

        # 把未被分类的摘要归入"其他"
        uncovered = all_indices - covered_indices
        if uncovered:
            valid_clusters["其他"] = list(uncovered)

        return valid_clusters if valid_clusters else {"综合": list(range(len(summaries)))}

    except Exception:
        # 出错时全部归为"综合"
        return {"综合": list(range(len(summaries)))}


def generate_wiki(summaries: list[dict], topic_hint: str = "") -> tuple[str, str]:
    """从摘要生成 Wiki 页面，返回 (title, content)"""
    from app.rag.agent import get_llm
    llm = get_llm(temperature=0.3)

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
    """从指定会话（或最近的摘要）distill 出 Wiki 页面

    自动按主题聚类，生成多篇 Wiki
    """
    # 获取摘要
    summaries = []
    if session_ids:
        for sid in session_ids:
            summaries.extend(get_knowledge_summaries(session_id=sid))
    else:
        summaries = get_knowledge_summaries(limit=50)

    if not summaries:
        return {"status": "error", "message": "没有可用的知识摘要"}

    # 按 question 去重，保留最新的摘要（后出现的覆盖先出现的）
    seen_questions: dict[str, dict] = {}
    for s in summaries:
        q = s.get("question", "").strip()
        if q:
            seen_questions[q] = s
    summaries = list(seen_questions.values())

    if not summaries:
        return {"status": "error", "message": "没有可用的知识摘要"}

    # 按主题聚类
    clusters = cluster_by_topic(summaries)

    # 为每个主题生成一篇 Wiki
    results = []
    source_sessions = list(set(s["session_id"] for s in summaries))

    for topic_name, indices in clusters.items():
        # 获取该主题的摘要
        topic_summaries = [summaries[i] for i in indices if i < len(summaries)]

        if not topic_summaries:
            continue

        # 生成 Wiki
        title, content = generate_wiki(topic_summaries, topic_hint=topic_name)

        # 保存
        save_wiki_page(
            title=title,
            content=content,
            topic=topic_name,
            source_sessions=source_sessions,
        )

        results.append({
            "title": title,
            "topic": topic_name,
            "summary_count": len(topic_summaries),
        })

    if not results:
        return {"status": "error", "message": "生成 Wiki 失败"}

    return {
        "status": "ok",
        "wiki_count": len(results),
        "wikis": results,
        "total_summaries": len(summaries),
    }
