"""API 路由注册"""

from fastapi import APIRouter, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import uuid

from app.models.schemas import ChatRequest, ChatResponse

api_router = APIRouter()


# ==================== 基础 ====================

@api_router.get("/health")
async def health_check():
    return {"status": "ok", "message": "三国历史知识库运行中"}


# ==================== 智能问答 ====================

@api_router.post("/chat")
async def chat(req: ChatRequest):
    """智能问答（Agentic RAG）"""
    from app.rag.agent import run_rag
    from app.rag.memory import remember_conversation

    session_id = req.session_id or str(uuid.uuid4())
    result = run_rag(req.question, session_id)

    # 自动记忆：存储对话 + 提取摘要 + 存入向量库
    try:
        remember_conversation(
            session_id=session_id,
            question=req.question,
            answer=result["answer"],
            sources=result["sources"],
            route=result["route"],
        )
    except Exception as e:
        print(f"记忆存储失败（不影响回答）: {e}")

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "route": result["route"],
        "sub_questions": result["sub_questions"],
        "session_id": session_id,
    }


@api_router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式智能问答（Agentic RAG，逐节点输出进度）"""
    from app.rag.agent import run_rag_stream
    from app.rag.memory import remember_conversation

    session_id = req.session_id or str(uuid.uuid4())

    async def event_generator():
        final_answer = ""
        sources = []
        route = ""
        sub_questions = []

        async for event in run_rag_stream(req.question, session_id):
            # 收集最终数据
            updates = event.get("updates", {})
            if "final_answer" in updates:
                final_answer = updates["final_answer"]
            if "sources" in updates:
                sources = updates["sources"]
            if "route" in updates:
                route = updates["route"]
            if "sub_questions" in updates:
                sub_questions = updates["sub_questions"]

            # 注入 session_id
            event["session_id"] = session_id
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 流结束后自动记忆
        if final_answer:
            try:
                remember_conversation(
                    session_id=session_id,
                    question=req.question,
                    answer=final_answer,
                    sources=sources,
                    route=route,
                )
            except Exception as e:
                print(f"记忆存储失败: {e}")

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ==================== 对话历史 ====================

@api_router.get("/sessions")
async def list_sessions(limit: int = Query(50, ge=1, le=200)):
    """获取最近的会话列表"""
    from app.core.database import get_recent_sessions
    return {"sessions": get_recent_sessions(limit)}


@api_router.get("/sessions/{session_id}")
async def get_session_history(session_id: str):
    """获取指定会话的对话历史"""
    from app.core.database import get_conversation_history
    return {"messages": get_conversation_history(session_id)}


# ==================== 知识摘要 ====================

@api_router.get("/knowledge")
async def list_knowledge(
    session_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """获取知识摘要列表"""
    from app.core.database import get_knowledge_summaries
    return {"summaries": get_knowledge_summaries(session_id, limit)}


# ==================== Wiki ====================

@api_router.get("/wiki")
async def list_wiki_pages(topic: str | None = Query(None)):
    """获取 Wiki 页面列表"""
    from app.core.database import get_wiki_pages
    return {"pages": get_wiki_pages(topic)}


@api_router.get("/wiki/{page_id}")
async def get_wiki_page_detail(page_id: int):
    """获取单篇 Wiki 页面"""
    from app.core.database import get_wiki_page
    page = get_wiki_page(page_id)
    if not page:
        return {"status": "error", "message": "页面不存在"}
    return page


class WikiDistillRequest(BaseModel):
    """Wiki distill 请求"""
    session_ids: list[str] | None = None
    topic: str = ""


@api_router.post("/wiki/distill")
async def distill_wiki(req: WikiDistillRequest):
    """从知识摘要 distill 出 Wiki 页面"""
    from app.rag.wiki import distill_and_save
    return distill_and_save(session_ids=req.session_ids, topic=req.topic)


# ==================== 语料入库 ====================

class IngestRequest(BaseModel):
    """入库请求"""
    clear_first: bool = False  # 是否先清空再入库
    force_reingest: bool = False  # 是否强制重新入库（忽略去重记录）


@api_router.post("/ingest")
async def ingest_data(req: IngestRequest | None = None):
    """触发语料入库流程（加载 raw/ 目录 → 切分 → embedding → Chroma）"""
    import uuid
    import asyncio
    from app.core.progress import tracker

    task_id = str(uuid.uuid4())[:8]
    tracker.create_task(task_id)
    clear = req.clear_first if req else False
    force = req.force_reingest if req else False

    # 后台运行
    async def run_ingest():
        from app.kg.pipeline import process_and_ingest_with_progress
        try:
            result = process_and_ingest_with_progress(task_id, clear_first=clear, force_reingest=force)
            tracker.update(task_id, done=True, message="入库完成")
        except Exception as e:
            tracker.update(task_id, done=True, error=str(e))

    asyncio.create_task(run_ingest())
    return {"status": "ok", "task_id": task_id, "clear_first": clear, "force_reingest": force}


@api_router.get("/ingest/progress/{task_id}")
async def ingest_progress_stream(task_id: str):
    """SSE 推送入库进度"""
    from app.core.progress import tracker

    async def event_generator():
        async for data in tracker.subscribe(task_id):
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            if data.get("done"):
                break
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@api_router.post("/ingest/upload")
async def upload_and_ingest(file: UploadFile = File(...)):
    """上传文件并入库（保存到 raw/ 目录后触发入库流程）"""
    import shutil
    from pathlib import Path
    from app.core.config import settings

    # 保存到 raw 目录
    raw_dir = Path(settings.raw_data_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / file.filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 触发入库
    from app.kg.pipeline import process_and_ingest
    result = process_and_ingest()

    return {
        "status": "ok",
        "filename": file.filename,
        "size": file_path.stat().st_size,
        "result": result,
    }


@api_router.get("/stats")
async def get_stats():
    """获取向量库统计信息"""
    from app.rag.vectorstore import get_vectorstore_stats
    try:
        stats = get_vectorstore_stats()
    except Exception:
        stats = {"count": 0, "collection_name": "N/A"}
    return stats


# ==================== 入库去重管理 ====================

@api_router.get("/ingestion/files")
async def get_ingestion_files():
    """获取已入库文件列表和 chunk 数量"""
    from app.kg.dedup import get_all_files
    files = get_all_files()
    return {"files": files}


@api_router.get("/ingestion/stats")
async def get_ingestion_stats():
    """获取入库统计信息"""
    from app.kg.dedup import get_ingestion_stats
    return get_ingestion_stats()


@api_router.get("/ingestion/files/{source_file:path}/chunks")
async def get_file_chunks(source_file: str):
    """获取指定文件的所有 chunk 记录"""
    from app.kg.dedup import get_file_chunks
    chunks = get_file_chunks(source_file)
    return {"chunks": chunks}


@api_router.delete("/ingestion/files/{source_file:path}")
async def delete_ingestion_file(source_file: str):
    """删除指定文件的入库记录和向量库中的对应 chunks"""
    from app.kg.dedup import delete_records_by_file
    from app.rag.vectorstore import get_vectorstore

    # 删除去重记录
    delete_records_by_file(source_file)

    # 删除向量库中的对应 chunks
    try:
        vectorstore = get_vectorstore()
        vectorstore.delete(where={"source": source_file})
    except Exception as e:
        print(f"删除向量库记录失败: {e}")

    return {"status": "ok", "deleted_file": source_file}


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    files: list[str]


@api_router.post("/ingestion/files/batch-delete")
async def batch_delete_ingestion_files(req: BatchDeleteRequest):
    """批量删除多个文件的入库记录和向量库中的对应 chunks"""
    from app.kg.dedup import delete_records_by_files
    from app.rag.vectorstore import get_vectorstore

    if not req.files:
        return {"status": "ok", "deleted_count": 0}

    # 删除去重记录
    delete_records_by_files(req.files)

    # 删除向量库中的对应 chunks
    try:
        vectorstore = get_vectorstore()
        for source_file in req.files:
            vectorstore.delete(where={"source": source_file})
    except Exception as e:
        print(f"删除向量库记录失败: {e}")

    return {"status": "ok", "deleted_count": len(req.files)}


@api_router.post("/ingestion/cleanup-duplicates")
async def cleanup_duplicates():
    """清理重复的 chunk 记录"""
    from app.kg.dedup import cleanup_duplicates
    cleaned_count = cleanup_duplicates()
    return {"status": "ok", "cleaned_count": cleaned_count}


# ==================== 原始文件管理 ====================

@api_router.get("/files")
async def list_raw_files():
    """获取 raw/ 目录下的文件列表"""
    from pathlib import Path
    from app.core.config import settings
    from app.tools.translator import SUPPORTED_EXTENSIONS

    raw_dir = Path(settings.raw_data_dir)
    if not raw_dir.exists():
        return {"files": []}

    files = []
    for filepath in sorted(raw_dir.rglob("*")):
        if filepath.is_file():
            # 判断文件类型
            suffix = filepath.suffix.lower()
            if suffix in {".txt", ".md", ".text", ".pdf"}:
                file_type = "可入库"
                status = "ready"
            elif suffix in SUPPORTED_EXTENSIONS:
                file_type = "需转换"
                # 检查是否已转换
                md_path = filepath.with_suffix(".md")
                if md_path.exists():
                    status = "converted"
                else:
                    status = "pending"
            else:
                file_type = "其他"
                status = "unsupported"

            files.append({
                "filename": filepath.name,
                "filepath": str(filepath.relative_to(raw_dir)),
                "size": filepath.stat().st_size,
                "modified": filepath.stat().st_mtime,
                "file_type": file_type,
                "status": status,
                "suffix": suffix,
            })

    return {"files": files}


class ConvertRequest(BaseModel):
    """格式转换请求"""
    filepath: str


@api_router.post("/files/convert")
async def convert_file(req: ConvertRequest):
    """转换指定文件"""
    from pathlib import Path
    from app.core.config import settings
    from app.tools.translator import convert_to_md

    raw_dir = Path(settings.raw_data_dir)
    file_path = raw_dir / req.filepath

    if not file_path.exists():
        return {"status": "error", "message": "文件不存在"}

    result = convert_to_md(str(file_path), str(raw_dir))

    return {
        "status": "ok" if result.success else "error",
        "message": result.message,
        "issues": result.issues,
    }


@api_router.delete("/files/{filepath:path}")
async def delete_raw_file(filepath: str):
    """删除指定文件"""
    from pathlib import Path
    from app.core.config import settings

    raw_dir = Path(settings.raw_data_dir)
    file_path = raw_dir / filepath

    if not file_path.exists():
        return {"status": "error", "message": "文件不存在"}

    file_path.unlink()

    return {"status": "ok", "deleted": filepath}


@api_router.get("/files/{filepath:path}/preview")
async def preview_file(filepath: str):
    """预览文件内容（前500字）"""
    from pathlib import Path
    from app.core.config import settings

    raw_dir = Path(settings.raw_data_dir)
    file_path = raw_dir / filepath

    if not file_path.exists():
        return {"status": "error", "message": "文件不存在"}

    try:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="gbk")

        preview = content[:500]
        if len(content) > 500:
            preview += "..."

        return {
            "status": "ok",
            "preview": preview,
            "total_length": len(content),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==================== 知识抽取 ====================

class ExtractRequest(BaseModel):
    """抽取请求"""
    text: str | None = None          # 直接传入文本
    chunk_ids: list[int] | None = None  # 或指定已入库的 chunk（暂不实现）


@api_router.post("/extract")
async def extract_knowledge(req: ExtractRequest):
    """从文本中抽取实体和关系（LLM），结果进入待审核队列"""
    from app.kg.extractor import extract_from_text
    from app.kg.review import add_to_review_queue

    if not req.text:
        return {"status": "error", "message": "请提供 text 参数"}

    result = extract_from_text(req.text)
    review_id = add_to_review_queue(result)

    return {
        "status": "ok",
        "review_id": review_id,
        "entities": [
            {
                "name": e.name,
                "entity_type": e.entity_type,
                "description": e.description,
                "courtesy_name": e.courtesy_name,
                "origin": e.origin,
                "year": e.year,
                "leader": e.leader,
            }
            for e in result.entities
        ],
        "relations": [
            {
                "source_name": r.source_name,
                "source_type": r.source_type,
                "target_name": r.target_name,
                "target_type": r.target_type,
                "relation_type": r.relation_type,
                "description": r.description,
            }
            for r in result.relations
        ],
    }


@api_router.post("/extract/batch")
async def extract_batch():
    """批量抽取：对 raw/ 目录下所有语料做知识抽取，结果进入审核队列"""
    from app.kg.corpus_import import load_all_documents
    from app.kg.text_splitter import split_document
    from app.kg.extractor import extract_from_chunks
    from app.kg.review import add_batch_to_review_queue

    documents = load_all_documents()
    if not documents:
        return {"status": "error", "message": "raw/ 目录下没有找到文档"}

    all_chunks = []
    for doc in documents:
        chunks = split_document(doc.content, doc.source, doc.category)
        all_chunks.extend(chunks)

    results = extract_from_chunks(all_chunks)
    review_ids = add_batch_to_review_queue(results)

    return {
        "status": "ok",
        "total_chunks": len(all_chunks),
        "extraction_results": len(results),
        "review_ids": review_ids,
    }


# ==================== 审核 ====================

@api_router.get("/review/pending")
async def get_pending_reviews():
    """获取所有待审核项"""
    from app.kg.review import get_pending_reviews
    return {"items": get_pending_reviews()}


@api_router.get("/review/stats")
async def get_review_stats():
    """获取审核统计"""
    from app.kg.review import get_review_stats
    return get_review_stats()


@api_router.get("/review/{review_id}")
async def get_review_detail(review_id: int):
    """获取审核项详情"""
    from app.kg.review import get_review_detail
    item = get_review_detail(review_id)
    if not item:
        return {"status": "error", "message": f"审核项 {review_id} 不存在"}
    return item


class ReviewApproveRequest(BaseModel):
    """审核通过请求（可选修正数据）"""
    edited_entities: list[dict] | None = None
    edited_relations: list[dict] | None = None


@api_router.post("/review/{review_id}/approve")
async def approve_review(review_id: int, req: ReviewApproveRequest | None = None):
    """审核通过，写入 SQLite"""
    from app.kg.review import approve_review as do_approve
    entities = req.edited_entities if req and req.edited_entities else None
    relations = req.edited_relations if req and req.edited_relations else None
    result = do_approve(review_id, entities, relations)
    return result


@api_router.post("/review/{review_id}/reject")
async def reject_review(review_id: int, reason: str = ""):
    """拒绝审核项"""
    from app.kg.review import reject_review as do_reject
    return do_reject(review_id, reason)


# ==================== 论文爬虫 ====================

class CrawlRequest(BaseModel):
    """爬取请求"""
    categories: list[str] | None = None  # 类别列表，None 表示全部
    max_per_keyword: int = 3
    download_pdfs: bool = False


@api_router.post("/crawl")
async def crawl_papers(req: CrawlRequest):
    """启动论文爬取管线（搜索 → 下载 → 解析 → 入库）"""
    from app.crawler.pipeline import crawl_and_ingest
    result = crawl_and_ingest(
        categories=req.categories,
        max_per_keyword=req.max_per_keyword,
        download_pdfs=req.download_pdfs,
    )
    return {"status": "ok", "result": result}


@api_router.get("/crawl/keywords")
async def list_keywords():
    """列出所有搜索关键词（按类别分组）"""
    from app.crawler.scholar import KEYWORD_CATEGORIES
    return KEYWORD_CATEGORIES


@api_router.get("/crawl/results")
async def get_crawl_results():
    """获取已有的爬取结果"""
    from pathlib import Path
    from app.core.config import settings
    results_file = Path(settings.raw_data_dir).parent / "processed" / "scholar_results.json"
    if not results_file.exists():
        return {"status": "ok", "papers": [], "count": 0}
    from app.crawler.scholar import load_search_results
    papers = load_search_results(str(results_file))
    return {
        "status": "ok",
        "papers": [
            {
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "abstract": p.abstract[:200] + "..." if len(p.abstract) > 200 else p.abstract,
                "keyword": p.keyword,
                "citation_count": p.citation_count,
            }
            for p in papers
        ],
        "count": len(papers),
    }


# ==================== 知识图谱 ====================

@api_router.get("/graph")
async def get_graph():
    """获取知识图谱数据（nodes + edges），供前端 G6 渲染"""
    from app.models.crud import get_all_entities, get_all_relations

    entities = get_all_entities()
    relations = get_all_relations()

    nodes = []
    id_map: dict[str, dict] = {}

    for etype in ["persons", "events", "forces"]:
        singular = etype.rstrip("s")
        for entity in entities[etype]:
            node_id = f"{singular}_{entity['id']}"
            nodes.append({
                "id": node_id,
                "data": {
                    "label": entity["name"],
                    "type": singular,
                    "description": entity.get("description", ""),
                },
            })
            id_map[f"{singular}:{entity['id']}"] = {"id": node_id}

    edges = []
    for rel in relations:
        src_key = f"{rel['source_type']}:{rel['source_id']}"
        tgt_key = f"{rel['target_type']}:{rel['target_id']}"
        if src_key in id_map and tgt_key in id_map:
            edges.append({
                "source": id_map[src_key]["id"],
                "target": id_map[tgt_key]["id"],
                "data": {
                    "label": rel["relation_type"],
                    "description": rel.get("description", ""),
                },
            })

    return {"nodes": nodes, "edges": edges}


@api_router.get("/graph/search")
async def search_graph(
    q: str = Query(..., description="搜索关键词"),
    entity_type: str | None = Query(None, description="实体类型过滤: person/event/force"),
):
    """搜索图谱中的实体"""
    from app.models.crud import get_all_entities, get_entity_relations
    from app.core.database import get_connection

    with get_connection() as conn:
        conditions = ["name LIKE ?"]
        params = [f"%{q}%"]

        if entity_type:
            table = f"{entity_type}s" if not entity_type.endswith("s") else entity_type
        else:
            table = None

        results = []
        tables = [table] if table else ["persons", "events", "forces"]

        for t in tables:
            singular = t.rstrip("s")
            rows = conn.execute(
                f"SELECT * FROM {t} WHERE name LIKE ?", [f"%{q}%"]
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                row_dict["entity_type"] = singular
                results.append(row_dict)

    return {"results": results, "count": len(results)}


@api_router.get("/graph/entity/{entity_type}/{entity_id}")
async def get_entity_detail(entity_type: str, entity_id: int):
    """获取实体详情及其关系"""
    from app.models.crud import get_entity_relations

    with get_connection_context() as conn:
        table = f"{entity_type}s" if not entity_type.endswith("s") else entity_type
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", [entity_id]).fetchone()

    if not row:
        return {"status": "error", "message": "实体不存在"}

    relations = get_entity_relations(entity_type, entity_id)

    return {
        "entity": dict(row),
        "entity_type": entity_type,
        "relations": relations,
    }


# 辅助：获取数据库连接的上下文
from contextlib import contextmanager

@contextmanager
def get_connection_context():
    from app.core.database import get_connection
    with get_connection() as conn:
        yield conn
