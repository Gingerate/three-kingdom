"""数据处理管线 —— 语料导入 → 切分 → embedding → 入库"""

from app.kg.corpus_import import load_all_documents, RawDocument
from app.kg.text_splitter import split_document, Chunk
from app.rag.vectorstore import add_chunks_to_vectorstore, get_vectorstore_stats, clear_vectorstore
from app.core.database import init_db


def process_and_ingest(raw_dir: str | None = None,
                       quantize: bool = True,
                       clear_first: bool = False,
                       force_reingest: bool = False) -> dict:
    """完整处理流程：加载文档 → 切分 → embedding → 写入 Chroma"""

    # 初始化数据库
    init_db()

    from app.kg.dedup import (
        init_dedup_table, calculate_chunk_hash, is_chunk_exists,
        add_records_batch, cleanup_all
    )

    # 如果强制重新入库，先清空去重记录
    if force_reingest:
        cleanup_all()
        print("已清空去重记录，将重新入库所有文件")

    # 1. 加载所有文档
    print("=" * 50)
    print("第 1 步：加载原始文档")
    documents = load_all_documents(raw_dir)
    print(f"共找到 {len(documents)} 个文档")
    for doc in documents:
        print(f"  - [{doc.category}] {doc.source} ({len(doc.content)} 字)")

    if not documents:
        print("没有找到任何文档，请将语料文件放入 backend/data/raw/ 目录")
        return {"documents": 0, "chunks": 0, "ingested": 0, "skipped": 0}

    # 2. 切分
    print("\n" + "=" * 50)
    print("第 2 步：文本切分")
    all_chunks: list[Chunk] = []
    for doc in documents:
        chunks = split_document(doc.content, doc.source, doc.category)
        all_chunks.extend(chunks)
        print(f"  - {doc.source}: {len(chunks)} 个文本块")
    print(f"共产生 {len(all_chunks)} 个文本块")

    # 3. 去重检查
    print("\n" + "=" * 50)
    print("第 3 步：去重检查")
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
            "chunk_index": chunk.chunk_index,
            "chunk_content": chunk.content[:500]  # 只保存前500字用于预览
        })

    print(f"新增 {len(new_chunks)} 个文本块，跳过 {skipped} 个已存在文本块")

    if not new_chunks:
        print("没有新的文本块需要入库")
        return {
            "documents": len(documents),
            "chunks": len(all_chunks),
            "ingested": 0,
            "skipped": skipped,
            "total_in_store": get_vectorstore_stats()['count'],
        }

    # 4. Embedding + 入库
    print("\n" + "=" * 50)
    print("第 4 步：Embedding + 写入向量库")
    from app.rag.embeddings import LocalHuggingFaceEmbeddings
    embeddings = LocalHuggingFaceEmbeddings(quantize=quantize)

    if clear_first:
        deleted = clear_vectorstore()
        print(f"已清空向量库，删除 {deleted} 条")

    ingested = add_chunks_to_vectorstore(new_chunks, embeddings)
    print(f"成功写入 {ingested} 条到向量库")

    # 5. 记录去重信息
    add_records_batch(records_to_add)
    print(f"已记录 {len(records_to_add)} 条去重信息")

    # 6. 统计
    stats = get_vectorstore_stats(embeddings)
    print("\n" + "=" * 50)
    print("处理完成！")
    print(f"  文档数: {len(documents)}")
    print(f"  文本块: {len(all_chunks)}")
    print(f"  新增入库: {ingested}")
    print(f"  跳过重复: {skipped}")
    print(f"  向量库总条数: {stats['count']}")

    return {
        "documents": len(documents),
        "chunks": len(all_chunks),
        "ingested": ingested,
        "skipped": skipped,
        "total_in_store": stats["count"],
    }


def process_and_ingest_with_progress(task_id: str, raw_dir: str | None = None,
                                      quantize: bool = True,
                                      clear_first: bool = False,
                                      force_reingest: bool = False) -> dict:
    """带进度推送的入库流程"""
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

    # 1. 加载文档
    update(stage="加载文档", message="正在扫描 raw/ 目录...")
    documents = load_all_documents(raw_dir)
    update(message=f"找到 {len(documents)} 个文档")

    if not documents:
        update(done=True, error="没有找到文档，请将语料放入 backend/data/raw/")
        return {"documents": 0, "chunks": 0, "ingested": 0, "skipped": 0}

    # 2. 切分
    update(stage="切分文本", message="正在切分...")
    all_chunks: list[Chunk] = []
    for i, doc in enumerate(documents):
        chunks = split_document(doc.content, doc.source, doc.category)
        all_chunks.extend(chunks)
        update(current=i + 1, total=len(documents),
               message=f"切分 {doc.source}: {len(chunks)} 块")

    update(message=f"共 {len(all_chunks)} 个文本块")

    # 3. 去重检查
    update(stage="去重检查", current=0, total=len(all_chunks),
           message="正在检查已入库内容...")
    new_chunks: list[Chunk] = []
    skipped = 0
    records_to_add = []

    for i, chunk in enumerate(all_chunks):
        chunk_hash = calculate_chunk_hash(chunk.content)
        if is_chunk_exists(chunk_hash):
            skipped += 1
            continue

        new_chunks.append(chunk)
        records_to_add.append({
            "chunk_hash": chunk_hash,
            "source_file": chunk.source,
            "chunk_index": chunk.chunk_index,
            "chunk_content": chunk.content[:500]  # 只保存前500字用于预览
        })

        # 每100个chunk更新一次进度
        if (i + 1) % 100 == 0:
            update(current=i + 1, total=len(all_chunks),
                   message=f"检查进度 {i + 1}/{len(all_chunks)}，新增 {len(new_chunks)}，跳过 {skipped}")

    update(message=f"去重完成：新增 {len(new_chunks)} 个文本块，跳过 {skipped} 个已存在文本块")

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
    update(stage="Embedding", current=0, total=len(new_chunks),
           message="加载 embedding 模型...")
    from app.rag.embeddings import LocalHuggingFaceEmbeddings
    from app.rag.vectorstore import get_vectorstore, clear_vectorstore
    from app.core.config import settings

    embeddings = LocalHuggingFaceEmbeddings(quantize=quantize)

    if clear_first:
        update(message="清空向量库...")
        deleted = clear_vectorstore()
        print(f"已清空向量库，删除 {deleted} 条")

    vectorstore = get_vectorstore(embeddings)

    # 批量入库，每批上报进度
    batch_size = 32
    ingested = 0

    for i in range(0, len(new_chunks), batch_size):
        batch = new_chunks[i:i + batch_size]
        texts = [c.content for c in batch]
        metadatas = [{
            "source": c.source,
            "category": c.category,
            "chapter": c.chapter,
            "chunk_index": c.chunk_index,
        } for c in batch]

        vectorstore.add_texts(texts=texts, metadatas=metadatas)
        ingested += len(batch)

        update(current=ingested, total=len(new_chunks),
               message=f"Embedding {ingested}/{len(new_chunks)}")

    # 5. 记录去重信息
    add_records_batch(records_to_add)
    print(f"已记录 {len(records_to_add)} 条去重信息")

    # 6. 完成
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


if __name__ == "__main__":
    process_and_ingest()
