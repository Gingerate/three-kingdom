"""爬虫管线 —— 搜索 → 下载 → 解析 → 入库"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.crawler.scholar import (
    search_all_categories, search_by_category,
    save_search_results, load_search_results,
    PaperMetadata,
)
from app.crawler.downloader import batch_download_pdfs, parse_all_pdfs
from app.kg.corpus_import import load_all_documents
from app.kg.text_splitter import split_document
from app.rag.vectorstore import add_chunks_to_vectorstore


def crawl_and_ingest(
    categories: list[str] | None = None,
    max_per_keyword: int = 3,
    download_pdfs: bool = False,
    skip_search: bool = False,
    results_file: str | None = None,
) -> dict:
    """完整爬取管线：搜索 → 下载 PDF → 解析 → 切分 → embedding → 入库

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
        print(f"跳过搜索，加载已有结果: {results_file}")
        papers = load_search_results(results_file)
    else:
        print("=" * 50)
        print("第 1 步：Google Scholar 搜索")

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
        return {"searched": 0, "downloaded": 0, "parsed": 0, "ingested": 0}

    # ==================== 第 2 步：下载 PDF ====================
    if download_pdfs:
        print("\n" + "=" * 50)
        print("第 2 步：下载 PDF")
        papers = batch_download_pdfs(papers)
    else:
        print("\n跳过 PDF 下载")

    # ==================== 第 3 步：解析 PDF ====================
    print("\n" + "=" * 50)
    print("第 3 步：解析 PDF")
    parsed = parse_all_pdfs()
    print(f"解析了 {len(parsed)} 个 PDF 文件")

    # ==================== 第 4 步：加载 + 切分 + 入库 ====================
    print("\n" + "=" * 50)
    print("第 4 步：加载文档 → 切分 → embedding → 入库")

    documents = load_all_documents()
    if not documents:
        print("没有找到可处理的文档")
        return {
            "searched": len(papers),
            "downloaded": len(parsed),
            "parsed": len(parsed),
            "ingested": 0,
        }

    all_chunks = []
    for doc in documents:
        chunks = split_document(doc.content, doc.source, doc.category)
        all_chunks.extend(chunks)

    print(f"共 {len(all_chunks)} 个文本块，开始 embedding...")

    from app.rag.embeddings import LocalHuggingFaceEmbeddings
    embeddings = LocalHuggingFaceEmbeddings()
    ingested = add_chunks_to_vectorstore(all_chunks, embeddings)

    print(f"\n{'='*50}")
    print(f"管线完成！")
    print(f"  搜索论文: {len(papers)} 篇")
    print(f"  解析 PDF: {len(parsed)} 个")
    print(f"  文本块: {len(all_chunks)} 个")
    print(f"  入库: {ingested} 条")

    return {
        "searched": len(papers),
        "downloaded": len(parsed),
        "parsed": len(parsed),
        "ingested": ingested,
    }
