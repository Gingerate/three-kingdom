"""Agentic RAG 状态机 —— 基于 LangGraph 的多步推理 RAG"""

from __future__ import annotations

import logging
import threading
from typing import TypedDict, Annotated
from operator import add as add_messages

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.core.config import settings
from app.prompts import load_prompt
from app.utils.parsers import parse_llm_json

logger = logging.getLogger(__name__)


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
    resolved_question: str              # 指代消解后的问题

    # 输出
    final_answer: str
    sources: list[str]


# ==================== LLM 实例（单例缓存） ====================

_llm_cache: dict[str, ChatOpenAI] = {}
_llm_lock = threading.Lock()


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """获取 LLM 实例（按 temperature 缓存单例）"""
    # 使用字符串 key 避免浮点数精度问题
    cache_key = f"{temperature:.2f}"
    if cache_key not in _llm_cache:
        with _llm_lock:
            if cache_key not in _llm_cache:
                _llm_cache[cache_key] = ChatOpenAI(
                    model=settings.llm_model,
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    temperature=temperature,
                    max_tokens=4096,
                )
    return _llm_cache[cache_key]


# ==================== 节点函数 ====================


def resolve_coreference(state: RAGState) -> dict:
    """指代消解：根据对话历史将问题中的代词替换为具体实体"""
    session_id = state.get("session_id", "")
    question = state["question"]

    # 如果没有 session_id，跳过指代消解
    if not session_id:
        return {"resolved_question": question}

    # 获取最近的对话历史
    try:
        from app.core.database import get_conversation_history
        history = get_conversation_history(session_id, limit=6)  # 最近 3 轮对话
    except Exception:
        return {"resolved_question": question}

    # 如果没有历史对话，跳过指代消解
    if not history or len(history) < 2:
        return {"resolved_question": question}

    # 构建对话历史文本
    history_text = ""
    for msg in history[-6:]:  # 最近 3 轮
        role = "用户" if msg["role"] == "user" else "助手"
        content = msg["content"][:200]  # 截取前 200 字
        history_text += f"{role}: {content}\n"

    # 检查问题中是否包含代词
    pronouns = ["他", "她", "它", "他们", "她们", "它们", "这个", "那个", "这些", "那些",
                "此人", "此人", "其", "其中", "该", "该人", "该事"]
    has_pronoun = any(pronoun in question for pronoun in pronouns)

    # 如果没有代词，跳过指代消解
    if not has_pronoun:
        return {"resolved_question": question}

    llm = get_llm()

    prompt = f"""根据对话历史，将用户问题中的代词（他、她、它、他们、这个、那个等）替换为具体的人名、事件或事物名称。

## 对话历史
{history_text}

## 用户问题
{question}

## 要求
1. 只替换明确的代词，不要改变问题的其他部分
2. 如果无法确定指代对象，保留原词
3. 只输出替换后的问题，不要添加其他内容

## 示例
对话历史：
用户: 诸葛亮的军事思想是什么？
助手: 诸葛亮的军事思想强调...

用户: 他有哪些著名的战役？
输出: 诸葛亮有哪些著名的战役？"""

    try:
        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="请进行指代消解"),
        ])

        resolved = response.content.strip()
        # 验证输出合理性（长度不能差异太大）
        if resolved and 0.5 * len(question) <= len(resolved) <= 2 * len(question):
            return {"resolved_question": resolved}
    except Exception as e:
        logger.warning(f"指代消解失败: {e}")

    return {"resolved_question": question}


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

    # 使用指代消解后的问题
    question = state.get("resolved_question") or state["question"]

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=question),
    ])

    route = response.content.strip().lower()
    if route not in ("simple", "complex"):
        route = "simple"

    return {"route": route}


def query_decomposition(state: RAGState) -> dict:
    """查询分解：将复杂问题拆解为子问题"""
    # 使用指代消解后的问题
    question = state.get("resolved_question") or state["question"]

    if state["route"] == "simple":
        return {"sub_questions": [question]}

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
        HumanMessage(content=question),
    ])

    data = parse_llm_json(response.content)
    sub_questions = data.get("sub_questions", [question]) if data else [question]

    return {"sub_questions": sub_questions}


def retrieve(state: RAGState) -> dict:
    """检索节点：从 Chroma 检索相关文档 + 从 SQLite 检索知识图谱"""
    from app.rag.vectorstore import search_vectorstore, search_memory

    all_docs = []
    seen_contents = set()

    # 使用指代消解后的问题，如果 sub_questions 为空（简单问题路由跳过了 decompose）
    resolved_question = state.get("resolved_question") or state["question"]
    questions = state["sub_questions"] or [resolved_question]
    session_id = state.get("session_id", "")

    for question in questions:
        # 检索主知识库
        docs = search_vectorstore(question, k=10)
        # 检索对话记忆（qa_memory collection，按 session_id 过滤）
        memory_docs = search_memory(question, k=5, session_id=session_id)
        for doc in docs + memory_docs:
            content_hash = hash(doc.page_content)
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                all_docs.append({
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", ""),
                    "chapter": doc.metadata.get("chapter", ""),
                    "category": doc.metadata.get("category", ""),
                })

    # 检索知识图谱（SQLite）
    kg_docs = _search_knowledge_graph(questions)
    for doc in kg_docs:
        content_hash = hash(doc["content"])
        if content_hash not in seen_contents:
            seen_contents.add(content_hash)
            all_docs.append(doc)

    return {"retrieved_docs": all_docs}


def _search_knowledge_graph(questions: list[str]) -> list[dict]:
    """从 SQLite 知识图谱中检索相关实体和关系"""
    from app.core.database import get_connection

    results = []
    try:
        with get_connection() as conn:
            for question in questions:
                # 搜索匹配的实体
                for table, type_name in [("persons", "人物"), ("events", "事件"), ("forces", "势力")]:
                    rows = conn.execute(
                        f"SELECT * FROM {table} WHERE name LIKE ? OR description LIKE ? LIMIT 5",
                        [f"%{question[:10]}%", f"%{question[:20]}%"],
                    ).fetchall()
                    for row in rows:
                        row_dict = dict(row)
                        content = f"【{type_name}】{row_dict['name']}"
                        if row_dict.get('description'):
                            content += f"：{row_dict['description']}"
                        if row_dict.get('courtesy_name'):
                            content += f"（字：{row_dict['courtesy_name']}）"
                        if row_dict.get('year'):
                            content += f"（时间：{row_dict['year']}）"
                        results.append({
                            "content": content,
                            "source": f"知识图谱-{type_name}",
                            "chapter": "",
                            "category": "knowledge_graph",
                        })

                # 搜索匹配的关系（使用唯一别名避免覆盖）
                rows = conn.execute(
                    """SELECT r.*,
                         CASE r.source_type
                           WHEN 'person' THEN sp.name
                           WHEN 'event' THEN se.name
                           WHEN 'force' THEN sf.name
                         END as src_name,
                         CASE r.target_type
                           WHEN 'person' THEN tp.name
                           WHEN 'event' THEN te.name
                           WHEN 'force' THEN tf.name
                         END as tgt_name
                       FROM relations r
                       LEFT JOIN persons sp ON r.source_type='person' AND r.source_id=sp.id
                       LEFT JOIN events se ON r.source_type='event' AND r.source_id=se.id
                       LEFT JOIN forces sf ON r.source_type='force' AND r.source_id=sf.id
                       LEFT JOIN persons tp ON r.target_type='person' AND r.target_id=tp.id
                       LEFT JOIN events te ON r.target_type='event' AND r.target_id=te.id
                       LEFT JOIN forces tf ON r.target_type='force' AND r.target_id=tf.id
                       WHERE r.description LIKE ?
                       LIMIT 10""",
                    [f"%{question[:20]}%"],
                ).fetchall()
                for row in rows:
                    row_dict = dict(row)
                    src_name = row_dict.get('src_name', row_dict['source_id'])
                    tgt_name = row_dict.get('tgt_name', row_dict['target_id'])
                    content = f"【关系】{src_name} --[{row_dict['relation_type']}]--> {tgt_name}"
                    if row_dict.get('description'):
                        content += f"：{row_dict['description']}"
                    results.append({
                        "content": content,
                        "source": "知识图谱-关系",
                        "chapter": "",
                        "category": "knowledge_graph",
                    })
    except Exception as e:
        logger.warning(f"知识图谱检索失败: {e}")

    return results[:10]  # 限制返回数量


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
        logger.warning(f"Reranker 不可用，使用 LLM 评分: {e}")

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

    # 使用指代消解后的问题
    question = state.get("resolved_question") or state["question"]

    # 使用 replace 而非 format，避免提示词中的花括号被误解析
    prompt = f"{identity}\n\n{rules}\n\n## 参考资料\n{{CONTEXT}}\n\n## 用户问题\n{{QUESTION}}"
    prompt = prompt.replace("{CONTEXT}", context).replace("{QUESTION}", question)

    response = llm.invoke([
        SystemMessage(content=prompt),
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

    data = parse_llm_json(response.content)
    passed = data.get("passed", False) if data else False  # 解析失败默认不通过，触发重试

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
    workflow.add_node("resolve", resolve_coreference)  # 指代消解
    workflow.add_node("router", query_router)
    workflow.add_node("decompose", query_decomposition)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade", relevance_grading)
    workflow.add_node("generate", generate)
    workflow.add_node("reflect", self_reflection)
    workflow.add_node("finalize", finalize)
    workflow.add_node("increment_retry", increment_retry)

    # 设置入口
    workflow.set_entry_point("resolve")

    # 添加边
    workflow.add_edge("resolve", "router")  # 指代消解后进入路由
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

# 全局图实例（带并发保护）
_rag_graph = None
_rag_graph_lock = threading.Lock()


def get_rag_graph():
    """获取 RAG 图实例（单例，线程安全）"""
    global _rag_graph
    if _rag_graph is None:
        with _rag_graph_lock:
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
        "resolved_question": "",
        "final_answer": "",
        "sources": [],
    }

    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"RAG 管线异常: {e}")
        return {
            "answer": f"抱歉，处理您的问题时出现了错误：{e}",
            "sources": [],
            "route": "error",
            "sub_questions": [],
        }

    return {
        "answer": result["final_answer"],
        "sources": result["sources"],
        "route": result["route"],
        "sub_questions": result["sub_questions"],
    }


async def run_rag_stream(question: str, session_id: str = ""):
    """流式运行 Agentic RAG（逐节点输出进度，不阻塞事件循环）"""
    import asyncio

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
        "resolved_question": "",
        "final_answer": "",
        "sources": [],
    }

    # 用 asyncio.Queue 桥接同步迭代器与异步生成器，避免阻塞事件循环
    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    def _run_sync():
        try:
            for event in graph.stream(initial_state, stream_mode="updates"):
                for node_name, updates in event.items():
                    queue.put_nowait({
                        "node": node_name,
                        "updates": {k: v for k, v in updates.items() if k != "retrieved_docs"},
                    })
        except Exception as e:
            logger.error(f"RAG 流式管线异常: {e}")
            queue.put_nowait({
                "node": "error",
                "updates": {"final_answer": f"抱歉，处理您的问题时出现了错误：{e}", "sources": []},
            })
        finally:
            queue.put_nowait(_SENTINEL)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_sync)

    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        yield item
