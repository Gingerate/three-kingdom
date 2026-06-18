"""Agentic RAG 状态机 —— 基于 LangGraph 的多步推理 RAG"""

from __future__ import annotations

import json
from typing import TypedDict, Annotated
from operator import add as add_messages

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.core.config import settings
from app.prompts import load_prompt


# ==================== 状态定义 ====================


class RAGState(TypedDict):
    """RAG Agent 的状态"""
    # 输入
    question: str
    session_id: str

    # 中间状态
    route: str                          # "simple" / "complex"
    sub_questions: list[str]            # 分解后的子问题
    retrieved_docs: list[dict]          # 检索到的文档
    graded_docs: list[dict]            # 评分后的文档
    generation: str                     # 生成的回答
    reflection_passed: bool             # 自我反思是否通过
    retry_count: int                    # 重试次数

    # 输出
    final_answer: str
    sources: list[str]


# ==================== LLM 实例 ====================


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,
        max_tokens=4096,
    )


# ==================== 节点函数 ====================


def query_router(state: RAGState) -> dict:
    """路由节点：判断问题是简单还是复杂"""
    llm = get_llm()

    prompt = """你是一个问题分类器。判断用户的问题是简单问题还是复杂问题。

简单问题：可以用单一检索直接回答的事实性问题。
复杂问题：需要多步推理、对比分析、或涉及多个实体/事件的问题。

只回复 "simple" 或 "complex"，不要回复其他内容。

示例：
- "官渡之战发生在哪一年？" → simple
- "对比诸葛亮和司马懿的军事思想" → complex
- "曹操的字是什么？" → simple
- "汉献帝如何联合世家诛灭董卓？" → complex
- "赤壁之战的经过" → simple
- "东汉末年的政治格局是怎样的？" → complex"""

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=state["question"]),
    ])

    route = response.content.strip().lower()
    if route not in ("simple", "complex"):
        route = "simple"

    return {"route": route}


def query_decomposition(state: RAGState) -> dict:
    """查询分解：将复杂问题拆解为子问题"""
    if state["route"] == "simple":
        return {"sub_questions": [state["question"]]}

    llm = get_llm()

    prompt = """你是一个问题分解助手。将用户的复杂问题分解为 2-4 个简单的子问题，每个子问题可以独立检索回答。

输出 JSON 格式：
{"sub_questions": ["子问题1", "子问题2", ...]}

示例：
问题：对比诸葛亮和司马懿的军事思想
{"sub_questions": ["诸葛亮的军事思想和战略特点是什么？", "司马懿的军事思想和战略特点是什么？", "诸葛亮和司马懿有过哪些直接的军事对抗？"]}

问题：汉献帝如何联合世家诛灭董卓？
{"sub_questions": ["汉献帝时期的朝廷权力结构是怎样的？", "王允在诛董卓事件中起了什么作用？", "吕布为什么背叛董卓？", "世家大族在东汉末年的政治影响力如何？"]}"""

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=state["question"]),
    ])

    try:
        text = response.content.strip()
        if "```json" in text:
            text = text[text.index("```json") + 7:text.index("```")].strip()
        elif "```" in text:
            text = text[text.index("```") + 3:text.index("```")].strip()
        data = json.loads(text)
        sub_questions = data.get("sub_questions", [state["question"]])
    except (json.JSONDecodeError, ValueError):
        sub_questions = [state["question"]]

    return {"sub_questions": sub_questions}


def retrieve(state: RAGState) -> dict:
    """检索节点：从 Chroma 检索相关文档"""
    from app.rag.vectorstore import search_vectorstore

    all_docs = []
    seen_contents = set()

    for question in state["sub_questions"]:
        docs = search_vectorstore(question, k=10)
        for doc in docs:
            content_hash = hash(doc.page_content)
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                all_docs.append({
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", ""),
                    "chapter": doc.metadata.get("chapter", ""),
                    "category": doc.metadata.get("category", ""),
                })

    return {"retrieved_docs": all_docs}


def relevance_grading(state: RAGState) -> dict:
    """相关性评分：筛选出与问题相关的文档"""
    if not state["retrieved_docs"]:
        return {"graded_docs": []}

    # 尝试用 Reranker 精排
    try:
        from app.rag.reranker import get_reranker
        from langchain_core.documents import Document

        reranker = get_reranker()
        docs_as_langchain = [
            Document(
                page_content=d["content"],
                metadata={"source": d["source"], "chapter": d["chapter"]},
            )
            for d in state["retrieved_docs"]
        ]

        # 合并所有子问题作为查询
        query = " ".join(state["sub_questions"])
        reranked = reranker.rerank(query, docs_as_langchain, top_k=5)

        graded = []
        for doc in reranked:
            graded.append({
                "content": doc.page_content,
                "source": doc.metadata.get("source", ""),
                "chapter": doc.metadata.get("chapter", ""),
                "category": doc.metadata.get("category", ""),
            })
        return {"graded_docs": graded}

    except Exception as e:
        print(f"Reranker 不可用，使用 LLM 评分: {e}")

    # Fallback：用 LLM 评分
    llm = get_llm()

    prompt = """你是文档相关性评分器。判断以下文档是否与问题相关。
对每个文档，输出 "relevant" 或 "irrelevant"。

问题：{question}

文档：
{docs}

逐行输出每个文档的判断结果，每行一个，格式：序号. relevant/irrelevant"""

    docs_text = "\n".join(
        f"{i+1}. [{d['source']}] {d['content'][:200]}..."
        for i, d in enumerate(state["retrieved_docs"][:10])
    )

    response = llm.invoke([
        SystemMessage(content=prompt.format(question=state["question"], docs=docs_text)),
        HumanMessage(content="请评分"),
    ])

    # 解析结果
    graded = []
    lines = response.content.strip().split("\n")
    for i, line in enumerate(lines):
        if i >= len(state["retrieved_docs"]):
            break
        if "relevant" in line.lower() and "irrelevant" not in line.lower():
            graded.append(state["retrieved_docs"][i])

    # 如果全部被过滤，保留前 3 个
    if not graded:
        graded = state["retrieved_docs"][:3]

    return {"graded_docs": graded[:5]}


def generate(state: RAGState) -> dict:
    """生成节点：基于检索结果生成回答"""
    llm = get_llm(temperature=0.3)

    # 构建上下文
    context_parts = []
    sources = []
    for i, doc in enumerate(state["graded_docs"], 1):
        source_info = f"[{doc['source']}"
        if doc.get("chapter"):
            source_info += f" - {doc['chapter']}"
        source_info += "]"
        context_parts.append(f"参考资料 {i} {source_info}：\n{doc['content']}")
        if doc["source"] not in sources:
            sources.append(doc["source"])

    context = "\n\n".join(context_parts)

    identity = load_prompt("identity")
    rules = load_prompt("rules")
    prompt = f"""{identity}

{rules}

## 参考资料
{{context}}

## 用户问题
{{question}}"""

    response = llm.invoke([
        SystemMessage(content=prompt.format(context=context, question=state["question"])),
        HumanMessage(content="请回答"),
    ])

    return {
        "generation": response.content,
        "sources": sources,
    }


def self_reflection(state: RAGState) -> dict:
    """自我反思：检查回答是否有依据，是否存在幻觉"""
    llm = get_llm()

    context = "\n\n".join(d["content"] for d in state["graded_docs"])

    prompt = """你是回答质量检查器。检查生成的回答是否基于提供的参考资料。

判断标准：
1. 回答中的事实是否能在参考资料中找到依据？
2. 是否存在编造的信息？
3. 回答是否完整地回应了用户的问题？

输出 JSON 格式：
{{"passed": true/false, "reason": "判断理由"}}

如果回答基本有依据且完整，passed 为 true。
如果回答存在明显编造或遗漏关键信息，passed 为 false。"""

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"""参考资料：
{context}

用户问题：{state['question']}

生成的回答：
{state['generation']}"""),
    ])

    try:
        text = response.content.strip()
        if "```json" in text:
            text = text[text.index("```json") + 7:text.index("```")].strip()
        elif "```" in text:
            text = text[text.index("```") + 3:text.index("```")].strip()
        data = json.loads(text)
        passed = data.get("passed", True)
    except (json.JSONDecodeError, ValueError):
        passed = True  # 解析失败默认通过

    return {"reflection_passed": passed}


def finalize(state: RAGState) -> dict:
    """最终输出"""
    return {
        "final_answer": state["generation"],
    }


# ==================== 条件路由 ====================


def should_decompose(state: RAGState) -> str:
    """判断是否需要查询分解"""
    return "decompose" if state["route"] == "complex" else "retrieve"


def should_retry(state: RAGState) -> str:
    """判断是否需要重试"""
    if state["reflection_passed"]:
        return "finalize"
    if state.get("retry_count", 0) >= 2:
        return "finalize"  # 最多重试 2 次
    return "retrieve"  # 重新检索


def increment_retry(state: RAGState) -> dict:
    """增加重试计数"""
    return {"retry_count": state.get("retry_count", 0) + 1}


# ==================== 构建图 ====================


def build_rag_graph() -> StateGraph:
    """构建 Agentic RAG 状态图"""

    workflow = StateGraph(RAGState)

    # 添加节点
    workflow.add_node("router", query_router)
    workflow.add_node("decompose", query_decomposition)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade", relevance_grading)
    workflow.add_node("generate", generate)
    workflow.add_node("reflect", self_reflection)
    workflow.add_node("finalize", finalize)
    workflow.add_node("increment_retry", increment_retry)

    # 设置入口
    workflow.set_entry_point("router")

    # 添加边
    workflow.add_conditional_edges(
        "router",
        should_decompose,
        {"decompose": "decompose", "retrieve": "retrieve"},
    )
    workflow.add_edge("decompose", "retrieve")
    workflow.add_edge("retrieve", "grade")
    workflow.add_edge("grade", "generate")
    workflow.add_edge("generate", "reflect")
    workflow.add_conditional_edges(
        "reflect",
        should_retry,
        {"finalize": "finalize", "retrieve": "increment_retry"},
    )
    workflow.add_edge("increment_retry", "retrieve")
    workflow.add_edge("finalize", END)

    return workflow.compile()


# ==================== 入口函数 ====================

# 全局图实例
_rag_graph = None


def get_rag_graph():
    """获取 RAG 图实例（单例）"""
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
    return _rag_graph


def run_rag(question: str, session_id: str = "") -> dict:
    """运行 Agentic RAG

    Args:
        question: 用户问题
        session_id: 会话 ID

    Returns:
        {"answer": str, "sources": list[str], "route": str}
    """
    graph = get_rag_graph()

    initial_state: RAGState = {
        "question": question,
        "session_id": session_id,
        "route": "",
        "sub_questions": [],
        "retrieved_docs": [],
        "graded_docs": [],
        "generation": "",
        "reflection_passed": False,
        "retry_count": 0,
        "final_answer": "",
        "sources": [],
    }

    result = graph.invoke(initial_state)

    return {
        "answer": result["final_answer"],
        "sources": result["sources"],
        "route": result["route"],
        "sub_questions": result["sub_questions"],
    }


async def run_rag_stream(question: str, session_id: str = ""):
    """流式运行 Agentic RAG（逐节点输出进度）"""
    graph = get_rag_graph()

    initial_state: RAGState = {
        "question": question,
        "session_id": session_id,
        "route": "",
        "sub_questions": [],
        "retrieved_docs": [],
        "graded_docs": [],
        "generation": "",
        "reflection_passed": False,
        "retry_count": 0,
        "final_answer": "",
        "sources": [],
    }

    # 使用 stream 模式
    for event in graph.stream(initial_state, stream_mode="updates"):
        for node_name, updates in event.items():
            yield {
                "node": node_name,
                "updates": {k: v for k, v in updates.items() if k != "retrieved_docs"},
            }
