"""PDF 解析器 —— 提取 PDF 正文为 Markdown"""

from __future__ import annotations

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFParseError(Exception):
    """PDF 解析失败"""
    pass


def parse_pdf_to_markdown(pdf_path: str | Path) -> str:
    """解析 PDF 为 Markdown 格式

    优先使用 pdfplumber 提取文本层。
    如果是图片型 PDF，自动 fallback 到 OCR。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        解析后的 Markdown 文本

    Raises:
        PDFParseError: 解析失败时抛出
        FileNotFoundError: 文件不存在时抛出
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    # Step 1: pdfplumber 文本提取
    try:
        import pdfplumber
    except ImportError:
        raise PDFParseError("pdfplumber 未安装")

    content = ""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            text_parts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            content = "\n\n".join(text_parts)
    except Exception as e:
        logger.warning(f"pdfplumber 提取失败: {e}")

    # Step 2: 如果提取为空，尝试 OCR
    if not content.strip():
        from app.tools.ocr import is_image_pdf, ocr_pdf
        if is_image_pdf(pdf_path):
            logger.info(f"检测到图片型 PDF，启用 OCR: {pdf_path.name}")
            content = ocr_pdf(pdf_path)

    if not content.strip():
        raise PDFParseError("PDF 解析结果为空，可能是扫描件或加密文件")

    # 后处理：移除参考文献
    content = remove_references(content)

    return content


def remove_references(text: str) -> str:
    """移除参考文献部分

    检测常见参考文献标题（中文/英文），截断其后内容。

    Args:
        text: 原始文本

    Returns:
        移除参考文献后的文本
    """
    patterns = [
        r"^##?\s*参考文献\s*$",
        r"^##?\s*References\s*$",
        r"^##?\s*Bibliography\s*$",
        r"^##?\s*REFERENCE[S]?\s*$",
    ]

    lines = text.split("\n")
    cutoff_index = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        for pattern in patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                cutoff_index = i
                logger.info(f"检测到参考文献标题，截断位置: 第 {i} 行")
                break
        if cutoff_index < len(lines):
            break

    if cutoff_index < len(lines):
        result = "\n".join(lines[:cutoff_index]).strip()
        logger.info(f"已移除参考文献，保留 {cutoff_index} 行")
        return result

    return text
