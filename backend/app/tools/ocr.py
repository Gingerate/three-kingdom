"""OCR 模块 —— 对图片型 PDF 进行文字识别

使用 PaddleOCR 进行中文 OCR，支持扫描版古籍文献。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 全局 PaddleOCR 实例（延迟初始化，避免重复加载模型）
_ocr_instance = None


def _get_ocr():
    """获取 PaddleOCR 单例（延迟初始化）"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_instance = PaddleOCR(
                lang="ch",           # 中文识别
            )
            logger.info("PaddleOCR 初始化完成")
        except ImportError:
            logger.error("PaddleOCR 未安装，请运行: pip install paddlepaddle paddleocr")
            raise
    return _ocr_instance


def is_image_pdf(filepath: str | Path, threshold: float = 0.1) -> bool:
    """检测 PDF 是否为图片型（扫描版）

    判断逻辑：如果大部分页面的文本密度低于阈值，则认为是图片型 PDF。

    Args:
        filepath: PDF 文件路径
        threshold: 文本密度阈值（字符数/页面面积），低于此值视为图片页

    Returns:
        True 表示图片型 PDF
    """
    try:
        import pdfplumber
    except ImportError:
        return False

    filepath = Path(filepath)
    if not filepath.exists():
        return False

    try:
        with pdfplumber.open(filepath) as pdf:
            if not pdf.pages:
                return False

            # 取前 5 页采样（避免大 PDF 耗时过长）
            sample_pages = pdf.pages[:5]
            image_pages = 0

            for page in sample_pages:
                text = page.extract_text() or ""
                # 计算文本密度：字符数 / 页面面积
                area = page.width * page.height
                if area > 0:
                    density = len(text.strip()) / area
                    if density < threshold:
                        image_pages += 1

            # 超过一半的采样页是图片页，则认为是图片型 PDF
            return image_pages > len(sample_pages) / 2

    except Exception as e:
        logger.warning(f"检测 PDF 类型失败 {filepath.name}: {e}")
        return False


def ocr_pdf(filepath: str | Path) -> str:
    """对图片型 PDF 进行 OCR 识别，返回提取的文本

    Args:
        filepath: PDF 文件路径

    Returns:
        OCR 识别的文本内容
    """
    filepath = Path(filepath)
    if not filepath.exists():
        logger.error(f"PDF 文件不存在: {filepath}")
        return ""

    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.error("pdf2image 未安装，请运行: pip install pdf2image")
        return ""

    try:
        ocr = _get_ocr()
    except ImportError:
        return ""

    logger.info(f"开始 OCR 识别: {filepath.name}")

    try:
        # 将 PDF 每页转为图片
        images = convert_from_path(str(filepath), dpi=200)
        logger.info(f"  共 {len(images)} 页")

        all_text = []
        for i, img in enumerate(images, 1):
            # PaddleOCR 识别（v3.x API）
            result = ocr.ocr(img)
            if result and result[0]:
                # 提取文本，按置信度排序后拼接
                page_lines = []
                for line in result[0]:
                    text = line[1][0]  # 识别文本
                    confidence = line[1][1]  # 置信度
                    if confidence > 0.5:  # 过滤低置信度结果
                        page_lines.append(text)
                page_text = "\n".join(page_lines)
                if page_text.strip():
                    all_text.append(page_text)

            if i % 10 == 0:
                logger.info(f"  已处理 {i}/{len(images)} 页")

        content = "\n\n".join(all_text)
        logger.info(f"  OCR 完成: {filepath.name}，提取 {len(content)} 字")
        return content

    except Exception as e:
        logger.error(f"OCR 识别失败 {filepath.name}: {e}")
        return ""
