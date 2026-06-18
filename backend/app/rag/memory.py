"""对话记忆模块 —— 自动提取精华摘要并存入向量库"""

from __future__ import annotations

import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.core.database import save_message, save_knowledge_summary


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
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.1,
        max_tokens=1024,
    )

    try:
        response = llm.invoke([
            SystemMessage(content=EXTRACT_PROMPT.format(question=question, answer=answer)),
            HumanMessage(content="请提取精华摘要"),
        ])

        text = response.content.strip()
        if "```json" in text:
            text = text[text.index("```json") + 7:text.index("```")].strip()
        elif "```" in text:
            text = text[text.index("```") + 3:text.index("```")].strip()

        data = json.loads(text)
        summaries = data.get("summaries", [])
        # 过滤空字符串
        return [s for s in summaries if s.strip()]
    except Exception as e:
        print(f"知识提取失败: {e}")
        return []


def extract_and_store(session_id: str, question: str, answer: str,
                      sources: list[str]) -> list[str]:
    """提取精华摘要并存储到数据库"""
    summaries = extract_knowledge(question, answer)

    for summary in summaries:
        save_knowledge_summary(
            session_id=session_id,
            question=question,
            summary=summary,
            sources=sources,
        )

    return summaries


# ==================== 向量库存储 ====================


def store_summaries_to_vectorstore(summaries: list[str], session_id: str,
                                   sources: list[str] | None = None):
    """将精华摘要存入 Chroma 的 qa_memory collection"""
    if not summaries:
        return

    try:
        from app.rag.vectorstore import get_vectorstore
        from langchain_core.documents import Document

        docs = [
            Document(
                page_content=s,
                metadata={
                    "source": "qa_memory",
                    "session_id": session_id,
                    "original_sources": ", ".join(sources or []),
                },
            )
            for s in summaries
        ]

        vectorstore = get_vectorstore(collection_name="qa_memory")
        vectorstore.add_documents(docs)
        print(f"已将 {len(summaries)} 条摘要存入 qa_memory 向量库")
    except Exception as e:
        print(f"存入向量库失败: {e}")


# ==================== 完整的记忆流程 ====================


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

    return summaries
