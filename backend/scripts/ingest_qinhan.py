"""将秦汉经济卷 .md 文件 embedding 入库"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.kg.text_splitter import split_document
from app.rag.vectorstore import add_chunks_to_vectorstore
from app.rag.embeddings import LocalHuggingFaceEmbeddings


def main():
    md_path = Path(__file__).parent.parent / "data" / "raw" / "中国经济通史_秦汉经济卷.md"

    if not md_path.exists():
        print(f"文件不存在: {md_path}")
        return

    print(f"读取: {md_path.name}")
    content = md_path.read_text(encoding="utf-8")
    print(f"总字符数: {len(content)}")

    # 切分
    chunks = split_document(content, source="中国经济通史·秦汉经济卷", category="史料")
    print(f"切分为 {len(chunks)} 个文本块")

    # Embedding
    print("开始 embedding...")
    embeddings = LocalHuggingFaceEmbeddings(device="cuda")

    from app.core.config import settings
    from langchain_chroma import Chroma

    vectorstore = Chroma(
        collection_name=settings.chroma_collection_name,
        embedding_function=embeddings,
        persist_directory=settings.chroma_persist_dir,
    )

    # 带进度条的批量入库
    batch_size = 32
    total = len(chunks)
    ingested = 0

    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.content for c in batch]
        metadatas = [{
            "source": c.source,
            "category": c.category,
            "chapter": c.chapter,
            "chunk_index": c.chunk_index,
        } for c in batch]

        vectorstore.add_texts(texts=texts, metadatas=metadatas)
        ingested += len(batch)

        # 进度条
        pct = ingested / total * 100
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"\r  {bar} {pct:5.1f}% ({ingested}/{total})", end="", flush=True)

    print()
    print(f"完成！入库 {ingested} 条")


if __name__ == "__main__":
    main()
