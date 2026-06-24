"""数据处理管线 —— 语料导入 → 切分 → embedding → 入库

注意：入库流程只读取已转换的 .md/.txt 文件，格式转换在上传阶段完成。
"""

import asyncio
import logging
import threading
from app.kg.corpus_import import load_raw_documents_only, RawDocument
from app.kg.text_splitter import split_document, Chunk
from app.rag.vectorstore import add_chunks_to_vectorstore, get_vectorstore_stats, clear_vectorstore
from app.core.database import init_db

logger = logging.getLogger(__name__)

# 入库锁：防止并发入库导致竞态条件
_ingest_lock = threading.Lock()
_is_ingesting = False


def process_and_ingest(raw_dir: str | None = None,
                       quantize: bool = True,
                       clear_first: bool = False,
                       force_reingest: bool = False,
                       files: list[str] | None = None) -> dict:
    """完整处理流程：加载文档 → 切分 → embedding → 写入 Chroma

    Args:
        files: 可选的文件路径列表（相对于 raw_dir），传入时只入库指定文件
    """

    global _is_ingesting

    # 检查是否已有入库任务在运行
    if not _ingest_lock.acquire(blocking=False):
        return {"error": "已有入库任务在运行，请稍后再试", "documents": 0, "chunks": 0, "ingested": 0, "skipped": 0}

    try:
        _is_ingesting = True

        # 初始化数据库
        init_db()

        from app.kg.dedup import (
            init_dedup_table, calculate_chunk_hash, is_chunk_exists,
            add_records_batch, cleanup_all
        )

        # 如果强制重新入库，先清空去重记录
        if force_reingest:
            cleanup_all()
            logger.info("已清空去重记录，将重新入库所有文件")

        # clear_first：在去重检查之前清空向量库和去重记录
        if clear_first:
            deleted = clear_vectorstore()
            logger.info(f"已清空向量库，删除 {deleted} 条")
            cleanup_all()
            logger.info("已同步清空去重记录")

        # 1. 加载文档（如果指定了 files，只加载指定文件，不全量扫描）
        logger.info("=" * 50)
        logger.info("第 1 步：加载原始文档")
        documents = load_raw_documents_only(raw_dir, files=files)

        if files:
            logger.info(f"指定入库 {len(files)} 个文件，匹配到 {len(documents)} 个文档")
        else:
            logger.info(f"共找到 {len(documents)} 个文档")
        for doc in documents:
            logger.info(f"  - [{doc.category}] {doc.source} ({len(doc.content)} 字)")

        if not documents:
            logger.warning("没有找到任何文档，请将语料文件放入 backend/data/raw/ 目录")
            return {"documents": 0, "chunks": 0, "ingested": 0, "skipped": 0}

        # 2. 切分
        logger.info("=" * 50)
        logger.info("第 2 步：文本切分")
        all_chunks: list[Chunk] = []
        for doc in documents:
            chunks = split_document(doc.content, doc.source, doc.category, doc.source_name)
            all_chunks.extend(chunks)
            logger.info(f"  - [{doc.source_name}] {doc.source}: {len(chunks)} 个文本块")
        logger.info(f"共产生 {len(all_chunks)} 个文本块")

        # 3. 去重检查
        logger.info("=" * 50)
        logger.info("第 3 步：去重检查")
        new_chunks: list[Chunk] = []
        skipped = 0
        records_to_add = []

        for chunk in all_chunks:
            chunk_hash = calculate_chunk_hash(chunk.content)
            if is_chunk_exists(chunk_hash):
                skipped += 1
                continue

            new_chunks.append(chunk)
            records_to_add.append({
                "chunk_hash": chunk_hash,
                "source_file": chunk.source,
                "source_name": chunk.source_name,
                "chunk_index": chunk.chunk_index,
                "chunk_content": chunk.content[:500]  # 只保存前500字用于预览
            })

        logger.info(f"新增 {len(new_chunks)} 个文本块，跳过 {skipped} 个已存在文本块")

        if not new_chunks:
            logger.info("没有新的文本块需要入库")
            return {
                "documents": len(documents),
                "chunks": len(all_chunks),
                "ingested": 0,
                "skipped": skipped,
                "total_in_store": get_vectorstore_stats()['count'],
            }

        # 4. Embedding + 入库
        logger.info("=" * 50)
        logger.info("第 4 步：Embedding + 写入向量库")
        from app.rag.embeddings import get_embeddings
        embeddings = get_embeddings()

        ingested = add_chunks_to_vectorstore(new_chunks, embeddings)
        logger.info(f"成功写入 {ingested} 条到向量库")

        # 5. 记录去重信息（向量库写入成功后再记录，若此步失败重试仅产生重复，不会丢数据）
        add_records_batch(records_to_add)
        logger.info(f"已记录 {len(records_to_add)} 条去重信息")

        # 7. 统计
        stats = get_vectorstore_stats(embeddings)
        logger.info("=" * 50)
        logger.info("处理完成！")
        logger.info(f"  文档数: {len(documents)}")
        logger.info(f"  文本块: {len(all_chunks)}")
        logger.info(f"  新增入库: {ingested}")
        logger.info(f"  跳过重复: {skipped}")
        logger.info(f"  向量库总条数: {stats['count']}")

        return {
            "documents": len(documents),
            "chunks": len(all_chunks),
            "ingested": ingested,
            "skipped": skipped,
            "total_in_store": stats["count"],
        }
    finally:
        _is_ingesting = False
        _ingest_lock.release()


def process_and_ingest_with_progress(task_id: str, raw_dir: str | None = None,
                                      quantize: bool = True,
                                      clear_first: bool = False,
                                      force_reingest: bool = False,
                                      files: list[str] | None = None,
                                      cancel_check: callable = None) -> dict:
    """带进度推送的入库流程

    Args:
        files: 可选的文件路径列表（相对于 raw_dir），传入时只入库指定文件
        cancel_check: 取消检查回调，返回 True 表示应取消
    """

    global _is_ingesting

    def check_cancelled():
        """检查是否已取消，如果是则抛出 CancelledError"""
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("用户取消")

    # 检查是否已有入库任务在运行
    if not _ingest_lock.acquire(blocking=False):
        from app.core.progress import tracker
        tracker.update(task_id, done=True, error="已有入库任务在运行，请稍后再试")
        return {"error": "已有入库任务在运行，请稍后再试", "documents": 0, "chunks": 0, "ingested": 0, "skipped": 0}

    try:
        _is_ingesting = True

        from app.core.progress import tracker

        def update(**kwargs):
            tracker.update(task_id, **kwargs)

        # 初始化数据库
        init_db()

        from app.kg.dedup import (
            calculate_chunk_hash, is_chunk_exists,
            add_records_batch, cleanup_all
        )

        # 如果强制重新入库，先清空去重记录
        if force_reingest:
            cleanup_all()
            update(message="已清空去重记录，将重新入库所有文件")

        # clear_first：在去重检查之前清空向量库和去重记录
        if clear_first:
            update(message="清空向量库...")
            deleted = clear_vectorstore()
            logger.info(f"已清空向量库，删除 {deleted} 条")
            cleanup_all()
            logger.info("已同步清空去重记录")

        # 1. 加载文档（如果指定了 files，只加载指定文件）
        check_cancelled()
        update(stage="加载文档", message="正在扫描 raw/ 目录...")
        documents = load_raw_documents_only(raw_dir, files=files)

        if files:
            update(message=f"指定入库 {len(files)} 个文件，匹配到 {len(documents)} 个文档")
        else:
            update(message=f"找到 {len(documents)} 个文档")

        if not documents:
            update(done=True, error="没有找到文档，请将语料放入 backend/data/raw/")
            return {"documents": 0, "chunks": 0, "ingested": 0, "skipped": 0}

        # 2. 切分
        check_cancelled()
        logger.info(f"开始切分 {len(documents)} 个文档...")
        update(stage="切分文本", message="正在切分...")
        all_chunks: list[Chunk] = []
        for i, doc in enumerate(documents):
            logger.info(f"切分文档 {i+1}/{len(documents)}: {doc.source} ({len(doc.content)} 字)")
            chunks = split_document(doc.content, doc.source, doc.category, doc.source_name)
            all_chunks.extend(chunks)
            logger.info(f"  → 完成: {len(chunks)} 块")
            update(current=i + 1, total=len(documents),
                   message=f"切分 [{doc.source_name}] {doc.source}: {len(chunks)} 块")

        update(message=f"共 {len(all_chunks)} 个文本块")
        logger.info(f"切分完成，共 {len(all_chunks)} 个文本块，开始去重检查...")

        # 3. 去重检查
        update(stage="去重检查", current=0, total=len(all_chunks),
               message="正在检查已入库内容...")
        new_chunks: list[Chunk] = []
        skipped = 0
        records_to_add = []

        for i, chunk in enumerate(all_chunks):
            # 每100个chunk检查一次取消
            if (i + 1) % 100 == 0:
                check_cancelled()

            chunk_hash = calculate_chunk_hash(chunk.content)
            if is_chunk_exists(chunk_hash):
                skipped += 1
                continue

            new_chunks.append(chunk)
            records_to_add.append({
                "chunk_hash": chunk_hash,
                "source_file": chunk.source,
                "source_name": chunk.source_name,
                "chunk_index": chunk.chunk_index,
                "chunk_content": chunk.content[:500]  # 只保存前500字用于预览
            })

            # 每100个chunk更新一次进度
            if (i + 1) % 100 == 0:
                update(current=i + 1, total=len(all_chunks),
                       message=f"检查进度 {i + 1}/{len(all_chunks)}，新增 {len(new_chunks)}，跳过 {skipped}")

        update(message=f"去重完成：新增 {len(new_chunks)} 个文本块，跳过 {skipped} 个已存在文本块")
        logger.info("去重完成，准备进入 embedding 步骤...")

        if not new_chunks:
            update(done=True, message=f"没有新的文本块需要入库（共 {len(all_chunks)} 个，全部已存在）")
            return {
                "documents": len(documents),
                "chunks": len(all_chunks),
                "ingested": 0,
                "skipped": skipped,
                "total_in_store": get_vectorstore_stats()['count'],
            }

        # 4. Embedding + 入库（带进度）
        check_cancelled()
        update(stage="Embedding", current=0, total=len(new_chunks),
               message="加载 embedding 模型...")
        from app.rag.embeddings import get_embeddings
        from app.rag.vectorstore import get_vectorstore, chunks_to_documents

        logger.info("加载 embedding 模型...")
        embeddings = get_embeddings()
        logger.info("embedding 模型加载完成")

        # 5. 写入向量库
        logger.info("获取向量库实例...")
        vectorstore = get_vectorstore(embeddings)
        docs = chunks_to_documents(new_chunks)
        logger.info(f"准备写入 {len(docs)} 个文档...")

        batch_size = 100
        ingested = 0

        for i in range(0, len(docs), batch_size):
            check_cancelled()
            batch = docs[i:i + batch_size]
            logger.info(f"写入批次 {i//batch_size + 1}/{(len(docs)-1)//batch_size + 1}...")
            vectorstore.add_documents(batch)
            ingested += len(batch)

            update(current=ingested, total=len(new_chunks),
                   message=f"Embedding {ingested}/{len(new_chunks)}")

        logger.info("写入完成，记录去重信息...")
        # 6. 记录去重信息（向量库写入成功后再记录，若此步失败重试仅产生重复，不会丢数据）
        add_records_batch(records_to_add)
        logger.info(f"已记录 {len(records_to_add)} 条去重信息")

        stats = get_vectorstore_stats()
        update(stage="完成", current=len(new_chunks), total=len(new_chunks), done=True,
               message=f"入库完成，新增 {ingested} 条，跳过 {skipped} 条，向量库共 {stats['count']} 条")

        return {
            "documents": len(documents),
            "chunks": len(all_chunks),
            "ingested": ingested,
            "skipped": skipped,
            "total_in_store": stats["count"],
        }
    finally:
        _is_ingesting = False
        _ingest_lock.release()


if __name__ == "__main__":
    process_and_ingest()
