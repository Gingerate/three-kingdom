"""Chroma 向量数据库管理 —— 语料入库与检索"""

from __future__ import annotations

import logging
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import settings
from app.rag.embeddings import get_embeddings, LocalHuggingFaceEmbeddings
from app.kg.text_splitter import Chunk

logger = logging.getLogger(__name__)


def get_vectorstore(embeddings: LocalHuggingFaceEmbeddings | None = None,
                    collection_name: str | None = None) -> Chroma:
    """获取 Chroma 向量库实例"""
    emb = embeddings or get_embeddings()
    return Chroma(
        collection_name=collection_name or settings.chroma_collection_name,
        embedding_function=emb,
        persist_directory=settings.chroma_persist_dir,
    )


def chunks_to_documents(chunks: list[Chunk]) -> list[Document]:
    """将 Chunk 转换为 LangChain Document"""
    docs = []
    for chunk in chunks:
        docs.append(Document(
            page_content=chunk.content,
            metadata={
                "source": chunk.source,
                "category": chunk.category,
                "chapter": chunk.chapter,
                "chunk_index": chunk.chunk_index,
                **chunk.metadata,
            },
        ))
    return docs


def clear_vectorstore(collection_name: str | None = None,
                      embeddings: LocalHuggingFaceEmbeddings | None = None) -> int:
    """清空向量库，返回删除的条数（分批删除，避免大集合 OOM）"""
    vectorstore = get_vectorstore(embeddings, collection_name)
    collection = vectorstore._collection
    count = collection.count()

    if count > 0:
        # 分批获取和删除，避免一次性加载所有数据到内存
        batch_size = 1000
        deleted = 0
        while True:
            batch = collection.get(limit=batch_size)
            if not batch["ids"]:
                break
            collection.delete(ids=batch["ids"])
            deleted += len(batch["ids"])

    return count


def add_chunks_to_vectorstore(chunks: list[Chunk],
                               embeddings: LocalHuggingFaceEmbeddings | None = None,
                               clear_first: bool = False) -> int:
    """将切分后的语料批量写入向量库，返回写入数量

    Args:
        clear_first: 是否先清空再写入（避免重复）
    """
    if not chunks:
        return 0

    vectorstore = get_vectorstore(embeddings)

    # 可选：先清空
    if clear_first:
        deleted = clear_vectorstore()
        logger.info(f"已清空向量库，删除 {deleted} 条")

    docs = chunks_to_documents(chunks)

    # 分批写入，每批 100 条（避免内存问题）
    batch_size = 100
    total = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i: i + batch_size]
        vectorstore.add_documents(batch)
        total += len(batch)
        logger.info(f"已写入 {total}/{len(docs)} 条")

    return total


def search_vectorstore(query: str, k: int = 20,
                        embeddings: LocalHuggingFaceEmbeddings | None = None) -> list[Document]:
    """语义检索，返回 top-k 相关文档"""
    vectorstore = get_vectorstore(embeddings)
    return vectorstore.similarity_search(query, k=k)


def search_memory(query: str, k: int = 5,
                  embeddings: LocalHuggingFaceEmbeddings | None = None,
                  session_id: str | None = None) -> list[Document]:
    """从对话记忆 collection 中检索相关历史摘要

    Args:
        query: 查询文本
        k: 返回数量
        embeddings: 可选的 embedding 模型
        session_id: 可选的会话 ID，用于过滤同一会话的记忆
    """
    try:
        vectorstore = get_vectorstore(embeddings, collection_name="qa_memory")
        # 如果指定了 session_id，只检索同一会话的记忆
        if session_id:
            return vectorstore.similarity_search(
                query, k=k, filter={"session_id": session_id}
            )
        return vectorstore.similarity_search(query, k=k)
    except Exception:
        # qa_memory collection 可能尚未创建（首次使用前），静默返回空
        return []


def get_vectorstore_stats(embeddings: LocalHuggingFaceEmbeddings | None = None) -> dict:
    """获取向量库统计信息"""
    vectorstore = get_vectorstore(embeddings)
    collection = vectorstore._collection
    return {
        "count": collection.count(),
        "collection_name": settings.chroma_collection_name,
    }
