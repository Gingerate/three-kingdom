"""API 路由注册"""

import os
import re
import asyncio
import logging
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import uuid
from dataclasses import asdict

from app.models.schemas import ChatRequest

logger = logging.getLogger(__name__)
api_router = APIRouter()

# 后台任务引用集合，防止 GC 提前回收
_background_tasks: set[asyncio.Task] = set()

# 表名白名单，防止 SQL 注入
_VALID_TABLES = {"persons", "events", "forces"}
_VALID_TYPES = {"person", "event", "force"}


def _safe_table_name(entity_type: str) -> str:
    """校验实体类型并返回安全的表名"""
    if entity_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的实体类型: {entity_type}，可选: {_VALID_TYPES}")
    return f"{entity_type}s"


def _safe_path(raw_dir, filepath: str):
    """校验文件路径，防止路径遍历攻击"""
    from pathlib import Path
    file_path = (raw_dir / filepath).resolve()
    raw_resolved = raw_dir.resolve()
    if not str(file_path).startswith(str(raw_resolved)):
        raise HTTPException(status_code=400, detail="非法文件路径")
    return file_path


# ==================== 基础 ====================

@api_router.get("/health")
async def health_check():
    return {"status": "ok", "message": "三国历史知识库运行中"}


# ==================== 智能问答 ====================

@api_router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式智能问答（Agentic RAG，逐节点输出进度）"""
    import asyncio
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

        yield "data: [DONE]\n\n"

        # 流结束后后台执行记忆提取（不阻塞 [DONE] 信号）
        if final_answer:
            async def _save_memory():
                try:
                    await asyncio.to_thread(
                        remember_conversation,
                        session_id=session_id,
                        question=req.question,
                        answer=final_answer,
                        sources=sources,
                        route=route,
                    )
                except Exception as e:
                    logger.error(f"记忆存储失败: {e}")
            _bg_task = asyncio.create_task(_save_memory())
            _background_tasks.add(_bg_task)
            _bg_task.add_done_callback(_background_tasks.discard)

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


@api_router.get("/sessions/stats")
async def get_session_stats():
    """获取对话统计信息"""
    from app.core.database import get_conversation_stats
    return get_conversation_stats()


@api_router.get("/health")
async def health_check():
    """系统健康检查"""
    import os
    from pathlib import Path
    from app.core.config import settings

    result = {
        "status": "ok",
        "database": False,
        "chromadb": False,
        "raw_files_count": 0,
        "embedding_model": settings.embedding_model_name,
    }

    # 检查数据库
    try:
        from app.core.database import get_conversation_stats
        get_conversation_stats()
        result["database"] = True
    except Exception:
        result["status"] = "degraded"

    # 检查 ChromaDB
    try:
        from app.rag.vectorstore import get_vectorstore
        vs = get_vectorstore()
        result["chromadb"] = True
    except Exception:
        result["status"] = "degraded"

    # 统计原始文件
    raw_dir = Path(settings.project_root) / "data" / "raw"
    if raw_dir.exists():
        result["raw_files_count"] = len(list(raw_dir.rglob("*.*")))

    return result


@api_router.get("/coverage")
async def get_source_coverage():
    """获取信源覆盖度统计"""
    from app.core.database import get_source_coverage
    return get_source_coverage()


@api_router.get("/sessions/{session_id}")
async def get_session_history(session_id: str):
    """获取指定会话的对话历史"""
    from app.core.database import get_conversation_history
    return {"messages": get_conversation_history(session_id)}


@api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话"""
    from app.core.database import delete_session
    deleted = delete_session(session_id)
    return {"deleted": deleted}


class FeedbackRequest(BaseModel):
    session_id: str
    question: str
    answer: str
    rating: str  # 'up' or 'down'
    comment: str = ""


@api_router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """提交对话反馈"""
    from app.core.database import save_feedback
    save_feedback(req.session_id, req.question, req.answer, req.rating, req.comment)
    return {"status": "ok"}


# ==================== 知识摘要 ====================

@api_router.get("/knowledge")
async def list_knowledge(
    session_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """获取知识摘要列表"""
    from app.core.database import get_knowledge_summaries
    return {"summaries": get_knowledge_summaries(session_id, limit)}


@api_router.get("/knowledge/stats")
async def get_knowledge_stats():
    """获取知识摘要统计信息"""
    from app.core.database import get_knowledge_summaries_stats
    return get_knowledge_summaries_stats()


@api_router.post("/knowledge/cleanup")
async def cleanup_knowledge(days: int = Query(30, ge=1, le=365)):
    """清理指定天数之前的知识摘要"""
    from app.core.database import cleanup_old_knowledge_summaries
    deleted = cleanup_old_knowledge_summaries(days)
    return {"status": "ok", "deleted_count": deleted, "days": days}


# ==================== Wiki ====================

@api_router.get("/wiki")
async def list_wiki_pages(topic: str | None = Query(None)):
    """获取 Wiki 页面列表（不包含完整内容）"""
    from app.core.database import get_wiki_pages
    return {"pages": get_wiki_pages(topic, include_content=False)}


@api_router.get("/wiki/{page_id}")
async def get_wiki_page_detail(page_id: int):
    """获取单篇 Wiki 页面（包含完整内容）"""
    from app.core.database import get_wiki_page
    page = get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return page


class WikiUpdateRequest(BaseModel):
    """Wiki 更新请求"""
    title: str | None = None
    content: str | None = None
    topic: str | None = None


@api_router.put("/wiki/{page_id}")
async def update_wiki_page(page_id: int, req: WikiUpdateRequest):
    """更新 Wiki 页面"""
    from app.core.database import update_wiki_page, get_wiki_page
    page = get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    update_wiki_page(page_id, title=req.title, content=req.content, topic=req.topic)
    return {"status": "ok", "message": "更新成功"}


@api_router.delete("/wiki/{page_id}")
async def delete_wiki_page(page_id: int):
    """删除 Wiki 页面"""
    from app.core.database import delete_wiki_page, get_wiki_page
    page = get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    delete_wiki_page(page_id)
    return {"status": "ok", "message": "删除成功"}


class WikiDistillRequest(BaseModel):
    """Wiki distill 请求"""
    session_ids: list[str] | None = None
    topic: str = ""


@api_router.post("/wiki/distill")
async def distill_wiki(req: WikiDistillRequest):
    """从知识摘要 distill 出 Wiki 页面"""
    import asyncio
    from app.rag.wiki import distill_and_save
    # 在线程池中执行，避免 LLM 调用阻塞事件循环
    return await asyncio.to_thread(distill_and_save, session_ids=req.session_ids, topic=req.topic)


# ==================== 语料入库 ====================

class IngestRequest(BaseModel):
    """入库请求"""
    clear_first: bool = False  # 是否先清空再入库
    force_reingest: bool = False  # 是否强制重新入库（忽略去重记录）
    files: list[str] | None = None  # 指定入库的文件列表（相对于 raw/ 目录的路径），为 None 时入库全部


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
    file_list = req.files if req else None

    # 后台运行（必须用 to_thread 避免阻塞事件循环）
    async def run_ingest():
        from app.kg.pipeline import process_and_ingest_with_progress
        try:
            await asyncio.to_thread(
                process_and_ingest_with_progress, task_id,
                clear_first=clear, force_reingest=force, files=file_list,
            )
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

    # 保存到 raw 目录（安全处理文件名）
    raw_dir = Path(settings.raw_data_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = os.path.basename(file.filename) if file.filename else "unnamed"
    if not safe_filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    file_path = raw_dir / safe_filename

    def _save_file():
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    await asyncio.to_thread(_save_file)

    # 触发入库（只入库刚上传的文件）
    from app.kg.pipeline import process_and_ingest
    result = await asyncio.to_thread(process_and_ingest, files=[safe_filename])

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
    import asyncio
    from app.kg.dedup import get_all_files
    files = await asyncio.to_thread(get_all_files)
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
        logger.error(f"删除向量库记录失败: {e}")

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

    # 先删除向量库中的对应 chunks（确保向量库删除成功后再删去重记录）
    vector_delete_ok = False
    try:
        vectorstore = get_vectorstore()
        for source_file in req.files:
            vectorstore.delete(where={"source": source_file})
        vector_delete_ok = True
    except Exception as e:
        logger.error(f"删除向量库记录失败: {e}")

    # 再删除去重记录
    if vector_delete_ok:
        delete_records_by_files(req.files)
    else:
        logger.warning("向量库删除失败，保留去重记录以避免重复入库")

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
    """获取 raw/ 目录下的文件列表（4 种状态：待转换/可入库/已入库/不支持）"""
    import asyncio
    from pathlib import Path
    from app.core.config import settings
    from app.tools.translator import SUPPORTED_EXTENSIONS
    from app.kg.dedup import get_all_files

    def _scan():
        raw_dir = Path(settings.raw_data_dir)
        if not raw_dir.exists():
            return []

        # 查询已入库文件集合（set 精确匹配，O(1) 查找）
        ingested_files = get_all_files()
        ingested_names = {f["source_file"] for f in ingested_files}

        files = []
        for filepath in sorted(raw_dir.rglob("*")):
            if not filepath.is_file():
                continue
            suffix = filepath.suffix.lower()

            # 基础状态判断（4 种：pending / ready / ingested / unsupported）
            if suffix in {".txt", ".md", ".text", ".pdf"}:
                status = "ready"
            elif suffix in SUPPORTED_EXTENSIONS:
                status = "ready" if filepath.with_suffix(".md").exists() else "pending"
            else:
                status = "unsupported"

            # 已入库检测：精确匹配文件名（去后缀）
            if status == "ready" and filepath.stem in ingested_names:
                status = "ingested"

            files.append({
                "filename": filepath.name,
                "filepath": str(filepath.relative_to(raw_dir)),
                "size": filepath.stat().st_size,
                "modified": filepath.stat().st_mtime,
                "status": status,
                "suffix": suffix,
            })

        return files

    files = await asyncio.to_thread(_scan)
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
    file_path = _safe_path(raw_dir, req.filepath)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    result = convert_to_md(str(file_path), str(raw_dir))

    return {
        "status": "ok" if result.success else "error",
        "message": result.message,
        "issues": result.issues,
    }


@api_router.delete("/files/{filepath:path}")
async def delete_raw_file(filepath: str):
    """删除指定文件及其关联的入库数据"""
    from pathlib import Path
    from app.core.config import settings

    raw_dir = Path(settings.raw_data_dir)
    file_path = _safe_path(raw_dir, filepath)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = file_path.name  # 含扩展名的文件名（与入库时 source 字段一致）

    # 1. 删除向量库中关联的数据（按 source 匹配）
    try:
        from app.rag.vectorstore import get_vectorstore
        vectorstore = get_vectorstore()
        vectorstore.delete(where={"source": filename})
    except Exception as e:
        logger.error(f"删除向量库记录失败: {e}")

    # 2. 删除去重记录
    try:
        from app.kg.dedup import delete_records_by_file
        delete_records_by_file(filename)
    except Exception as e:
        logger.error(f"删除去重记录失败: {e}")

    # 3. 删除原始文件
    file_path.unlink()

    # 4. 如果是 epub 等格式，也删除自动生成的 .md 文件
    md_path = file_path.with_suffix(".md")
    if md_path.exists() and md_path != file_path:
        md_path.unlink()

    return {"status": "ok", "deleted": filepath}


@api_router.get("/files/{filepath:path}/preview")
async def preview_file(filepath: str):
    """预览文件内容（前500字）"""
    from pathlib import Path
    from app.core.config import settings

    raw_dir = Path(settings.raw_data_dir)
    file_path = _safe_path(raw_dir, filepath)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 检查是否为二进制文件
    binary_extensions = {'.pdf', '.epub', '.docx', '.doc', '.xls', '.xlsx', '.ppt', '.pptx'}
    if file_path.suffix.lower() in binary_extensions:
        return {
            "status": "ok",
            "preview": f"[{file_path.suffix.upper()[1:]} 文件] 此文件类型需要转换为 Markdown 后才能预览内容。",
            "total_length": file_path.stat().st_size,
            "is_binary": True,
        }

    try:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="gbk")
            except UnicodeDecodeError:
                return {
                    "status": "ok",
                    "preview": "[无法解码的文本文件] 文件编码不是 UTF-8 或 GBK。",
                    "total_length": file_path.stat().st_size,
                    "is_binary": True,
                }

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
        raise HTTPException(status_code=400, detail="请提供 text 参数")

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
    import asyncio
    from app.core.progress import tracker

    task_id = str(uuid.uuid4())[:8]
    tracker.create_task(task_id)

    async def run_extract():
        from app.kg.corpus_import import load_all_documents
        from app.kg.text_splitter import split_document
        from app.kg.extractor import extract_from_chunks
        from app.kg.review import add_batch_to_review_queue

        try:
            tracker.update(task_id, stage="加载文档", message="正在加载 raw/ 目录下的文档...")
            documents = load_all_documents()
            if not documents:
                tracker.update(task_id, done=True, error="raw/ 目录下没有找到文档")
                return

            tracker.update(task_id, stage="切分文本", message=f"已加载 {len(documents)} 个文档，正在切分...")
            all_chunks = []
            for i, doc in enumerate(documents):
                chunks = split_document(doc.content, doc.source, doc.category)
                all_chunks.extend(chunks)
                tracker.update(task_id, current=i + 1, total=len(documents),
                             message=f"切分文档 {i + 1}/{len(documents)}: {doc.source}")

            tracker.update(task_id, stage="知识抽取", total=len(all_chunks), current=0,
                         message=f"共 {len(all_chunks)} 个文本块，开始抽取...")

            # 分批抽取，更新进度
            batch_size = 10
            all_results = []
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i:i + batch_size]
                batch_results = extract_from_chunks(batch)
                all_results.extend(batch_results)
                tracker.update(task_id, current=min(i + batch_size, len(all_chunks)),
                             message=f"已抽取 {len(all_results)} 个结果")

            tracker.update(task_id, stage="保存结果", message="正在将抽取结果加入审核队列...")
            review_ids = add_batch_to_review_queue(all_results)

            tracker.update(task_id, done=True,
                         message=f"完成！共抽取 {len(all_results)} 个结果，已加入审核队列")
        except Exception as e:
            tracker.update(task_id, done=True, error=str(e))

    asyncio.create_task(run_extract())
    return {"status": "ok", "task_id": task_id}


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
        raise HTTPException(status_code=404, detail=f"审核项 {review_id} 不存在")
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
    import asyncio
    from app.crawler.pipeline import crawl_and_ingest
    # 在线程池中执行，避免同步阻塞事件循环
    result = await asyncio.to_thread(
        crawl_and_ingest,
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
    import asyncio
    from pathlib import Path
    from app.core.config import settings
    from app.crawler.scholar import load_search_results

    def _load():
        results_file = Path(settings.raw_data_dir).parent / "processed" / "scholar_results.json"
        if not results_file.exists():
            return []
        return load_search_results(str(results_file))

    papers = await asyncio.to_thread(_load)

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
                "url": p.url,
                "pdf_url": p.pdf_url,
                "source": p.source,
                "journal": p.journal,
            }
            for p in papers
        ],
        "count": len(papers),
    }


@api_router.delete("/crawl/results/{index}")
async def delete_crawl_result(index: int):
    """删除指定索引的爬取结果"""
    from pathlib import Path
    from app.core.config import settings
    results_file = Path(settings.raw_data_dir).parent / "processed" / "scholar_results.json"
    if not results_file.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    from app.crawler.scholar import load_search_results
    papers = load_search_results(str(results_file))

    if index < 0 or index >= len(papers):
        raise HTTPException(status_code=400, detail="索引越界")

    removed = papers.pop(index)

    # 保存回文件
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in papers], f, ensure_ascii=False, indent=2)

    return {"status": "ok", "message": f"已删除: {removed.title}"}


@api_router.post("/crawl/ingest/{index}")
async def ingest_crawl_result(index: int):
    """将指定索引的论文导入知识库（下载 PDF → 解析正文 → 入库）"""
    import uuid
    import asyncio
    from pathlib import Path
    from app.core.config import settings
    from app.core.progress import tracker

    results_file = Path(settings.raw_data_dir).parent / "processed" / "scholar_results.json"
    if not results_file.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    from app.crawler.scholar import load_search_results
    papers = load_search_results(str(results_file))

    if index < 0 or index >= len(papers):
        raise HTTPException(status_code=400, detail="索引越界")

    paper = papers[index]

    # 检查是否有 PDF 链接
    if not paper.pdf_url:
        raise HTTPException(status_code=400, detail="该论文没有 PDF 下载链接")

    # 生成安全文件名
    safe_title = re.sub(r'[^\w\s-]', '', paper.title)[:50].strip()
    if not safe_title:
        safe_title = "untitled"

    # 下载 PDF（已存在则跳过）
    from app.crawler.downloader import download_pdf
    try:
        pdf_path = download_pdf(paper.pdf_url, filename=f"{safe_title}.pdf")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF 下载失败: {e}")

    # 解析 PDF 为 Markdown
    from app.crawler.pdf_parser import parse_pdf_to_markdown, PDFParseError
    try:
        body_content = parse_pdf_to_markdown(pdf_path)
    except PDFParseError as e:
        raise HTTPException(status_code=422, detail=f"PDF 解析失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF 解析失败: {e}")

    # 组装元数据头 + 正文
    content = f"# {paper.title}\n\n"
    content += f"**作者**: {', '.join(paper.authors)}\n"
    content += f"**年份**: {paper.year}\n"
    content += f"**来源**: {paper.source}\n"
    content += f"**引用数**: {paper.citation_count}\n\n"
    content += f"## 摘要\n\n{paper.abstract}\n\n"
    content += f"## 正文\n\n{body_content}\n"

    if paper.url:
        content += f"\n**原文链接**: {paper.url}\n"

    # 保存到 raw 目录
    filename = f"paper_{safe_title}.md"
    filepath = Path(settings.raw_data_dir) / filename
    filepath.write_text(content, encoding="utf-8")

    # 异步入库（embedding + 写入向量库）
    task_id = str(uuid.uuid4())[:8]
    tracker.create_task(task_id)

    async def run_ingest():
        from app.kg.pipeline import process_and_ingest_with_progress
        try:
            await asyncio.to_thread(process_and_ingest_with_progress, task_id, files=[filename])
            tracker.update(task_id, done=True, message="入库完成")
        except Exception as e:
            tracker.update(task_id, done=True, error=str(e))

    asyncio.create_task(run_ingest())

    return {
        "status": "ok",
        "message": f"已提交入库任务: {paper.title}",
        "task_id": task_id,
        "filename": filename,
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
    from app.core.database import get_connection

    if entity_type and entity_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的实体类型: {entity_type}，可选: {_VALID_TYPES}")

    # 转义 LIKE 通配符
    escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    with get_connection() as conn:
        if entity_type:
            tables = [_safe_table_name(entity_type)]
        else:
            tables = ["persons", "events", "forces"]

        results = []
        for t in tables:
            # 表名来自白名单，安全
            singular = t.rstrip("s")
            rows = conn.execute(
                f"SELECT * FROM {t} WHERE name LIKE ?", [f"%{escaped_q}%"]
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                row_dict["entity_type"] = singular
                results.append(row_dict)

    return {"results": results, "count": len(results)}


@api_router.get("/graph/entity/{entity_type}/{entity_id}")
async def get_entity_detail(entity_type: str, entity_id: int):
    """获取实体详情及其关系（关联实体名称）"""
    from app.core.database import get_connection

    table = _safe_table_name(entity_type)
    with get_connection() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", [entity_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="实体不存在")
        entity = dict(row)

        # 查询关系并关联实体名称
        rows = conn.execute(
            "SELECT * FROM relations WHERE (source_type=? AND source_id=?) OR (target_type=? AND target_id=?)",
            (entity_type, entity_id, entity_type, entity_id)
        ).fetchall()

        relations = []
        for r in rows:
            r_dict = dict(r)
            # 查询源实体名称（表名来自数据库，需校验）
            src_type = r_dict['source_type']
            if src_type in _VALID_TYPES:
                src_table = f"{src_type}s"
                src_row = conn.execute(f"SELECT name FROM {src_table} WHERE id = ?", [r_dict['source_id']]).fetchone()
                r_dict['source_name'] = src_row['name'] if src_row else str(r_dict['source_id'])
            else:
                r_dict['source_name'] = str(r_dict['source_id'])

            # 查询目标实体名称
            tgt_type = r_dict['target_type']
            if tgt_type in _VALID_TYPES:
                tgt_table = f"{tgt_type}s"
                tgt_row = conn.execute(f"SELECT name FROM {tgt_table} WHERE id = ?", [r_dict['target_id']]).fetchone()
                r_dict['target_name'] = tgt_row['name'] if tgt_row else str(r_dict['target_id'])
            else:
                r_dict['target_name'] = str(r_dict['target_id'])

            relations.append(r_dict)

    return {
        "entity": entity,
        "entity_type": entity_type,
        "relations": relations,
    }
