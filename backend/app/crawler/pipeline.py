"""爬虫管线 —— 搜索 → 下载 → 解析 → 入库（带去重）"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.crawler.scholar import (
    search_all_categories, search_by_category,
    save_search_results, load_search_results,
    PaperMetadata,
)
from app.crawler.downloader import batch_download_pdfs

logger = logging.getLogger(__name__)


def crawl_and_ingest(
    categories: list[str] | None = None,
    max_per_keyword: int = 3,
    download_pdfs: bool = False,
    skip_search: bool = False,
    results_file: str | None = None,
) -> dict:
    """完整爬取管线：搜索 → 下载 PDF → 切分 → embedding → 入库

    Args:
        categories: 要搜索的类别列表，None 表示全部
        max_per_keyword: 每个关键词最大结果数
        download_pdfs: 是否下载 PDF（需要有 PDF 链接）
        skip_search: 跳过搜索，直接使用已有的 results_file
        results_file: 已有的搜索结果 JSON 文件路径

    Returns:
        处理统计
    """
    processed_dir = Path(settings.raw_data_dir).parent / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ==================== 第 1 步：搜索 ====================
    if skip_search and results_file:
        logger.info(f"跳过搜索，加载已有结果: {results_file}")
        papers = load_search_results(results_file)
    else:
        logger.info("=" * 50)
        logger.info("第 1 步：Google Scholar 搜索")

        if categories:
            all_papers = []
            for cat in categories:
                papers = search_by_category(cat, max_per_keyword=max_per_keyword)
                all_papers.extend(papers)
            papers = all_papers
        else:
            papers = search_all_categories(max_per_keyword=max_per_keyword)

        # 保存搜索结果
        results_path = str(processed_dir / "scholar_results.json")
        save_search_results(papers, results_path)

    if not papers:
        return {"searched": 0, "downloaded": 0, "ingested": 0}

    # ==================== 第 2 步：下载 PDF ====================
    if download_pdfs:
        logger.info("=" * 50)
        logger.info("第 2 步：下载 PDF")
        papers = batch_download_pdfs(papers)
    else:
        logger.info("跳过 PDF 下载")

    # ==================== 第 3 步：加载 + 切分 + 入库 ====================
    logger.info("=" * 50)
    logger.info("第 3 步：加载文档 → 切分 → embedding → 入库")

    from app.kg.text_splitter import split_document

    # 加载所有文档（文本 + PDF，含质量门禁）
    from app.kg.corpus_import import load_all_documents
    documents = load_all_documents()

    if not documents:
        logger.info("没有找到可处理的文档")
        return {
            "searched": len(papers),
            "downloaded": 0,
            "ingested": 0,
        }

    all_chunks = []
    for doc in documents:
        chunks = split_document(doc.content, doc.source, doc.category)
        all_chunks.extend(chunks)

    logger.info(f"共 {len(all_chunks)} 个文本块，开始 embedding...")

    # 使用带去重的入库
    from app.rag.vectorstore import add_chunks_to_vectorstore
    from app.rag.embeddings import get_embeddings
    from app.core.database import init_db
    from app.kg.dedup import calculate_chunk_hash, is_chunk_exists, add_records_batch

    init_db()
    embeddings = get_embeddings()

    # 去重过滤
    new_chunks = []
    records_to_add = []
    skipped = 0

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
            "chunk_content": chunk.content[:500],
        })

    if not new_chunks:
        logger.info("所有文本块已存在，跳过入库")
        return {
            "searched": len(papers),
            "downloaded": 0,
            "ingested": 0,
            "skipped": skipped,
        }

    ingested = add_chunks_to_vectorstore(new_chunks, embeddings)
    add_records_batch(records_to_add)

    logger.info("=" * 50)
    logger.info("管线完成！")
    logger.info(f"  搜索论文: {len(papers)} 篇")
    logger.info(f"  文本块: {len(all_chunks)} 个")
    logger.info(f"  新增入库: {ingested} 条")
    logger.info(f"  跳过重复: {skipped} 条")

    return {
        "searched": len(papers),
        "downloaded": 0,
        "ingested": ingested,
        "skipped": skipped,
    }
