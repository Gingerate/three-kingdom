"""Embedding 模块 —— stella-mrl-large-zh-v3.5-1792d，BNB 4-bit 量化，1024d 输出"""

from __future__ import annotations

import logging
import threading
import torch
from langchain_core.embeddings import Embeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalHuggingFaceEmbeddings(Embeddings):
    """本地 Hugging Face embedding 模型，支持 BNB 4-bit 量化和 MRL 降维"""

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        target_dim: int | None = None,
        quantize: bool = True,
    ):
        self.model_path = model_path or settings.embedding_model_path
        self.device = device or settings.embedding_device
        self.target_dim = target_dim or settings.embedding_dim
        self.quantize = quantize
        self._model = None
        self._tokenizer = None
        self._load_lock = threading.Lock()

    def _load_model(self):
        """延迟加载模型（线程安全）"""
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return

            from transformers import AutoModel
            from transformers import BertTokenizer

            logger.info(f"正在加载 embedding 模型: {self.model_path}")

            # BertTokenizer 只需要 vocab.txt，不依赖 tokenizer_config.json
            logger.info("加载 tokenizer...")
            self._tokenizer = BertTokenizer.from_pretrained(self.model_path)
            logger.info("tokenizer 加载完成")

            if self.quantize:
                try:
                    from bitsandbytes import BitsAndBytesConfig

                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_quant_type="nf4",
                    )
                    self._model = AutoModel.from_pretrained(
                        self.model_path,
                        quantization_config=bnb_config,
                        device_map=self.device,
                    )
                except ImportError:
                    logger.warning("bitsandbytes 未安装，跳过量化，使用 FP16")
                    self._model = AutoModel.from_pretrained(
                        self.model_path,
                        torch_dtype=torch.float16,
                    ).to(self.device)
            else:
                self._model = AutoModel.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,
                ).to(self.device)

            self._model.eval()
            logger.info(f"模型加载完成，目标维度: {self.target_dim}")

    def _embed(self, text: str) -> list[float]:
        """单条文本 embedding"""
        self._load_model()

        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        ).to(self._model.device)

        with torch.no_grad(), torch.amp.autocast(device_type="cuda", enabled=self.device == "cuda"):
            outputs = self._model(**inputs)

        # Mean pooling
        attention_mask = inputs["attention_mask"]
        token_embeddings = outputs.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        embedding = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )

        # L2 归一化
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)

        # MRL 降维：截取前 target_dim 维
        embedding = embedding[:, : self.target_dim]

        return embedding[0].cpu().float().tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量 embedding 多条文本（支持批量推理）"""
        if not texts:
            return []

        self._load_model()

        # 小批量直接逐条处理
        if len(texts) <= 4:
            return [self._embed(text) for text in texts]

        # 批量推理（GPU 可承载更大 batch）
        batch_size = 128 if self.device == "cuda" else 32
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            inputs = self._tokenizer(
                batch,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            ).to(self._model.device)

            with torch.no_grad(), torch.amp.autocast(device_type="cuda", enabled=self.device == "cuda"):
                outputs = self._model(**inputs)

            # Mean pooling
            attention_mask = inputs["attention_mask"]
            token_embeddings = outputs.last_hidden_state
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            embeddings = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
                input_mask_expanded.sum(1), min=1e-9
            )

            # L2 归一化
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

            # MRL 降维
            embeddings = embeddings[:, :self.target_dim]

            all_embeddings.extend(embeddings.cpu().float().tolist())

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """embedding 查询文本"""
        return self._embed(text)


# 全局单例（线程安全）
_embedding_instance: LocalHuggingFaceEmbeddings | None = None
_embedding_lock = threading.Lock()


def get_embeddings() -> LocalHuggingFaceEmbeddings:
    """获取 embedding 模型单例（线程安全）"""
    global _embedding_instance
    if _embedding_instance is None:
        with _embedding_lock:
            if _embedding_instance is None:
                _embedding_instance = LocalHuggingFaceEmbeddings()
    return _embedding_instance
