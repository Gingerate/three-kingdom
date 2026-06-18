"""对话记忆模块 —— 自动提取精华摘要并存入向量库"""

from __future__ import annotations

import logging
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.core.database import save_message, save_knowledge_summary
from app.utils.parsers import parse_llm_json

logger = logging.getLogger(__name__)


# ==================== 对话存储 ====================


def store_conversation(session_id: str, question: str, answer: str,
                       sources: list[str], route: str):
    """存储一轮对话（问题+回答）"""
    save_message(session_id, "user", question)
    save_message(session_id, "assistant", answer, sources=sources, route=route)


# ==================== 精华提取 ====================


EXTRACT_PROMPT = """你是一个知识提炼专家。从以下问答对中提取 3-5 句精华摘要。

## 要求
1. 摘要必须忠于回答内容，不要添加回答中没有的信息
2. 每条摘要是一句完整的、可独立理解的知识陈述
3. 保留关键的人名、时间、地点、事件
4. 去除引用格式和过渡语句，只保留核心知识
5. 输出 JSON 格式

## 输出格式
{"summaries": ["知识陈述1", "知识陈述2", ...]}

## 问答对
问题：{question}

回答：{answer}"""


def extract_knowledge(question: str, answer: str) -> list[str]:
    """从问答对中提取精华摘要"""
    from app.rag.agent import get_llm

    llm = get_llm(temperature=0.1)

    try:
        response = llm.invoke([
            SystemMessage(content=EXTRACT_PROMPT.format(question=question, answer=answer)),
            HumanMessage(content="请提取精华摘要"),
        ])

        data = parse_llm_json(response.content)
        if not data:
            return []

        # 兼容多种返回格式
        summaries = data.get("summaries", [])
        if not summaries:
            summaries = data.get("summary", [])
        if not summaries and isinstance(data, list):
            summaries = data
        if not summaries and isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list) and v:
                    summaries = v
                    break

        # 过滤空字符串
        return [s for s in summaries if isinstance(s, str) and s.strip()]
    except Exception as e:
        logger.warning(f"知识提取失败: {type(e).__name__}: {e}")
        return []


# ==================== 向量库存储 ====================


def store_summaries_to_vectorstore(summaries: list[str], session_id: str,
                                   sources: list[str] | None = None):
    """将精华摘要存入 Chroma 的 qa_memory collection"""
    if not summaries:
        return

    try:
        from app.rag.vectorstore import get_vectorstore
        from langchain_core.documents import Document

        now = datetime.now().isoformat()
        docs = [
            Document(
                page_content=s,
                metadata={
                    "source": "qa_memory",
                    "session_id": session_id,
                    "original_sources": ", ".join(sources or []),
                    "created_at": now,
                },
            )
            for s in summaries
        ]

        vectorstore = get_vectorstore(collection_name="qa_memory")
        vectorstore.add_documents(docs)
        logger.info(f"已将 {len(summaries)} 条摘要存入 qa_memory 向量库")
    except Exception as e:
        logger.error(f"存入向量库失败: {e}")


# ==================== 完整的记忆流程 ====================


def cleanup_qa_memory(max_size: int = 5000):
    """清理 qa_memory 向量库，保留最新的 max_size 条记录

    Args:
        max_size: 最大保留记录数
    """
    try:
        from app.rag.vectorstore import get_vectorstore
        vectorstore = get_vectorstore(collection_name="qa_memory")
        collection = vectorstore._collection
        count = collection.count()

        if count > max_size:
            # 获取所有 ID 及其 metadata，按时间戳排序后删除最旧的
            excess = count - max_size
            all_data = collection.get(include=["metadatas"])
            if all_data["ids"]:
                # 按 metadata 中的 created_at 排序（无时间戳的排最前）
                id_meta_pairs = list(zip(all_data["ids"], all_data["metadatas"]))
                id_meta_pairs.sort(key=lambda x: x[1].get("created_at", "") if x[1] else "")
                oldest_ids = [pid for pid, _ in id_meta_pairs[:excess]]
                collection.delete(ids=oldest_ids)
                logger.info(f"已清理 {len(oldest_ids)} 条旧的 qa_memory 记录")
    except Exception as e:
        logger.error(f"清理 qa_memory 失败: {e}")


def remember_conversation(session_id: str, question: str, answer: str,
                          sources: list[str], route: str):
    """完整的一次性记忆流程：存储对话 + 提取摘要 + 存入向量库"""
    # 1. 存储对话记录
    store_conversation(session_id, question, answer, sources, route)

    # 2. 提取精华摘要
    summaries = extract_knowledge(question, answer)

    # 3. 存入 SQLite
    for summary in summaries:
        save_knowledge_summary(
            session_id=session_id,
            question=question,
            summary=summary,
            sources=sources,
        )

    # 4. 存入 Chroma qa_memory collection
    store_summaries_to_vectorstore(summaries, session_id, sources)

    # 5. 定期清理 qa_memory（每次对话后检查）
    cleanup_qa_memory()

    return summaries
