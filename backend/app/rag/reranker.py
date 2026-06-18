"""Reranker 模块 —— bge-reranker-v2-m3，对检索结果精排"""

from __future__ import annotations

import threading
from langchain_core.documents import Document

from app.core.config import settings, get_default_device


class LocalReranker:
    """本地 Reranker，基于交叉编码器"""

    def __init__(self, model_path: str | None = None, device: str | None = None):
        self.model_path = model_path or settings.reranker_model_path
        self.device = device or get_default_device()
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return

        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        print(f"正在加载 Reranker 模型: {self.model_path}, 设备: {self.device}")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        # CUDA 使用 float16 加速，其他设备使用 float32
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_path,
            torch_dtype=dtype,
        ).to(self.device)
        self._model.eval()
        print("Reranker 模型加载完成")

    def compute_score(self, query: str, passages: list[str]) -> list[float]:
        """计算 query-passage 相关性分数

        Args:
            query: 查询文本
            passages: 候选段落列表

        Returns:
            每个段落的相关性分数
        """
        import torch

        self._load_model()

        scores = []
        # 分批处理，每批 8 条
        batch_size = 8
        for i in range(0, len(passages), batch_size):
            batch = passages[i: i + batch_size]
            pairs = [[query, p] for p in batch]

            inputs = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self._model.device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                batch_scores = outputs.logits.squeeze(-1).cpu().float().tolist()

            if isinstance(batch_scores, float):
                batch_scores = [batch_scores]
            scores.extend(batch_scores)

        return scores

    def rerank(self, query: str, documents: list[Document], top_k: int = 5) -> list[Document]:
        """对文档列表重排序

        Args:
            query: 查询文本
            documents: 候选文档列表
            top_k: 返回前 k 个

        Returns:
            重排序后的 top-k 文档
        """
        if not documents:
            return []

        passages = [doc.page_content for doc in documents]
        scores = self.compute_score(query, passages)

        # 按分数降序排列
        scored_docs = sorted(zip(scores, documents), key=lambda x: x[0], reverse=True)

        return [doc for _, doc in scored_docs[:top_k]]


# 全局单例（带并发保护）
_reranker_instance: LocalReranker | None = None
_reranker_lock = threading.Lock()


def get_reranker() -> LocalReranker:
    """获取 Reranker 单例（线程安全）"""
    global _reranker_instance
    if _reranker_instance is None:
        with _reranker_lock:
            if _reranker_instance is None:
                _reranker_instance = LocalReranker()
    return _reranker_instance
