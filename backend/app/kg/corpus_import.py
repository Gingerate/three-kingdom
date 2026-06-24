"""语料导入模块 —— 读取 raw/ 目录下的文本文件，解析元数据

支持自动转换：.docx/.html/.rtf/.odt/.epub 等格式会自动转为 .md 后再处理
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from app.core.config import settings


@dataclass
class RawDocument:
    """原始文档"""
    filename: str
    filepath: str
    content: str
    source: str      # 实际文件路径（相对于 raw/ 目录）
    source_name: str  # 语义标识（如 "三国志", "三国演义"）
    category: str    # 分类（正史/演义/论文/史料）


def detect_source(filename: str) -> tuple[str, str]:
    """根据文件名推断来源和分类"""
    name = filename.lower()

    # 正史（一级）
    if "三国志" in name or "sgz" in name:
        return "三国志", "正史"
    elif "后汉书" in name:
        return "后汉书", "正史"
    elif "史记" in name:
        return "史记", "正史"
    elif "资治通鉴" in name:
        return "资治通鉴", "正史"
    elif "两汉纪" in name or "后汉纪" in name:
        return "两汉纪", "正史"
    elif "汉书" in name:
        return "汉书", "正史"
    elif "晋书" in name:
        return "晋书", "正史"
    elif "裴注" in name or "裴松之" in name:
        return "裴松之注", "正史"
    # 演义（二级）
    elif "三国演义" in name or "sgyy" in name or "演义" in name:
        return "三国演义", "演义"
    # 野史（三级）
    elif "世说新语" in name:
        return "世说新语", "野史"
    elif "搜神记" in name:
        return "搜神记", "野史"
    elif "风俗通义" in name:
        return "风俗通义", "野史"
    # 论文
    elif "论文" in name or "paper" in name:
        return f"论文_{filename}", "论文"
    else:
        return filename, "其他"


def auto_convert(raw_dir: Path, files: list[str] | None = None) -> int:
    """自动将 raw/ 目录下非标准文本格式转为 .md

    Args:
        raw_dir: raw/ 目录路径
        files: 可选的文件路径列表（相对于 raw_dir），传入时只转换指定文件

    Returns:
        成功转换的文件数
    """
    from app.tools.translator import convert_to_md, SUPPORTED_EXTENSIONS

    # 如果指定了文件列表，只转换指定的文件
    if files:
        files_to_convert = []
        for f in files:
            filepath = raw_dir / f
            if filepath.exists() and filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
                files_to_convert.append(filepath)
            # 也检查对应的源文件（如果传入的是 .md 路径，找对应的 epub 等）
            elif filepath.suffix.lower() == '.md':
                for ext in SUPPORTED_EXTENSIONS:
                    source = filepath.with_suffix(ext)
                    if source.exists():
                        files_to_convert.append(source)
                        break
    else:
        files_to_convert = [
            f for f in sorted(raw_dir.rglob("*"))
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    converted = 0
    for filepath in files_to_convert:
        result = convert_to_md(str(filepath), str(raw_dir))
        if result.success:
            converted += 1
            logger.info(f"  ✓ {result.message}")
            if result.issues:
                for issue in result.issues:
                    logger.warning(f"    ⚠ {issue}")
        else:
            logger.warning(f"  ✗ {result.message}")

    return converted


def load_raw_documents(raw_dir: str | None = None, files: list[str] | None = None) -> list[RawDocument]:
    """加载 raw/ 目录下文本文件（含自动格式转换）

    Args:
        raw_dir: raw/ 目录路径
        files: 可选的文件路径列表（相对于 raw_dir），传入时只加载指定文件
    """
    raw_path = Path(raw_dir or settings.raw_data_dir)
    if not raw_path.exists():
        raw_path.mkdir(parents=True, exist_ok=True)
        return []

    # 先自动转换非标准格式（只转换指定文件）
    from app.tools.translator import SUPPORTED_EXTENSIONS
    if files:
        # 只检查指定文件是否有需要转换的
        has_convertible = any(
            (raw_path / f).suffix.lower() in SUPPORTED_EXTENSIONS
            for f in files if (raw_path / f).exists()
        )
    else:
        has_convertible = any(
            f.suffix.lower() in SUPPORTED_EXTENSIONS
            for f in raw_path.rglob("*") if f.is_file()
        )

    if has_convertible:
        logger.info("检测到非标准格式文件，自动转换中...")
        auto_convert(raw_path, files=files)

    # 加载可读文本文件
    documents = []
    supported_ext = {".txt", ".md", ".text"}

    if files:
        # 只加载指定的文件
        file_paths = []
        for f in files:
            filepath = raw_path / f
            if filepath.exists() and filepath.is_file():
                if filepath.suffix.lower() in supported_ext:
                    file_paths.append(filepath)
                else:
                    # 尝试找对应的 .md 文件（可能已转换）
                    md_path = filepath.with_suffix('.md')
                    if md_path.exists():
                        file_paths.append(md_path)
    else:
        file_paths = sorted(raw_path.rglob("*"))

    for filepath in file_paths:
        if filepath.is_file() and filepath.suffix.lower() in supported_ext:
            try:
                try:
                    content = filepath.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = filepath.read_text(encoding="gbk")

                if not content.strip():
                    continue

                source_name, category = detect_source(filepath.stem)  # 用 stem 去掉扩展名
                # 使用相对于 raw/ 的路径作为 source
                relative_path = str(filepath.relative_to(raw_path))
                documents.append(RawDocument(
                    filename=filepath.name,
                    filepath=str(filepath),
                    content=content,
                    source=relative_path,
                    source_name=source_name,
                    category=category,
                ))
            except Exception as e:
                logger.warning(f"无法读取文件 {filepath}: {e}")

    return documents


def load_pdf_documents(raw_dir: str | None = None, files: list[str] | None = None) -> list[RawDocument]:
    """加载 raw/ 目录下的 PDF 文件（学术论文）

    Args:
        raw_dir: raw/ 目录路径
        files: 可选的文件路径列表（相对于 raw_dir），传入时只加载指定的 PDF 文件
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber 未安装，跳过 PDF 文件")
        return []

    raw_path = Path(raw_dir or settings.raw_data_dir)
    documents = []

    if files:
        # 只加载指定的 PDF 文件
        pdf_paths = []
        for f in files:
            if f.lower().endswith('.pdf'):
                filepath = raw_path / f
                if filepath.exists():
                    pdf_paths.append(filepath)
    else:
        pdf_paths = sorted(raw_path.rglob("*.pdf"))

    for filepath in pdf_paths:
        try:
            content = ""
            with pdfplumber.open(filepath) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                content = "\n\n".join(text_parts)

            if not content.strip():
                logger.info(f"跳过图片型 PDF（无法提取文本）: {filepath.name}")
                continue
            source_name, category = detect_source(filepath.name)
            # 使用相对于 raw/ 的路径作为 source
            relative_path = str(filepath.relative_to(raw_path))
            documents.append(RawDocument(
                filename=filepath.name,
                filepath=str(filepath),
                content=content,
                source=relative_path,
                source_name=source_name,
                category=category,
            ))
        except Exception as e:
            logger.warning(f"无法解析 PDF {filepath}: {e}")

    return documents


def load_raw_documents_only(raw_dir: str | None = None, files: list[str] | None = None) -> list[RawDocument]:
    """加载 raw/ 目录下已转换的文本文件（.md/.txt），不做格式转换

    这是入库流程专用函数，假设文件已经在上传阶段完成了格式转换和质量检查。

    Args:
        raw_dir: raw/ 目录路径
        files: 可选的文件路径列表（相对于 raw_dir），传入时只加载指定文件

    Returns:
        RawDocument 列表
    """
    raw_path = Path(raw_dir or settings.raw_data_dir)
    if not raw_path.exists():
        raw_path.mkdir(parents=True, exist_ok=True)
        return []

    # 只加载可读文本文件
    documents = []
    supported_ext = {".txt", ".md", ".text"}
    skipped_files = []

    if files:
        # 只加载指定的文件
        file_paths = []
        for f in files:
            filepath = raw_path / f
            if filepath.exists() and filepath.is_file():
                if filepath.suffix.lower() in supported_ext:
                    file_paths.append(filepath)
                else:
                    skipped_files.append(filepath.name)
    else:
        all_files = sorted(raw_path.rglob("*"))
        file_paths = []
        for filepath in all_files:
            if filepath.is_file():
                if filepath.suffix.lower() in supported_ext:
                    file_paths.append(filepath)
                elif filepath.suffix.lower():  # 有扩展名的文件
                    skipped_files.append(filepath.name)

    # 记录被跳过的文件
    if skipped_files:
        logger.warning(f"跳过 {len(skipped_files)} 个非文本格式文件（可能未完成格式转换）: {skipped_files[:10]}")

    for filepath in file_paths:
        if filepath.is_file() and filepath.suffix.lower() in supported_ext:
            try:
                try:
                    content = filepath.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = filepath.read_text(encoding="gbk")

                if not content.strip():
                    continue

                source_name, category = detect_source(filepath.stem)
                relative_path = str(filepath.relative_to(raw_path))
                documents.append(RawDocument(
                    filename=filepath.name,
                    filepath=str(filepath),
                    content=content,
                    source=relative_path,
                    source_name=source_name,
                    category=category,
                ))
            except Exception as e:
                logger.warning(f"无法读取文件 {filepath}: {e}")

    return documents


def load_all_documents(raw_dir: str | None = None, files: list[str] | None = None, auto_convert_flag: bool = True) -> list[RawDocument]:
    """加载所有文档（文本 + PDF，可选自动转换，含质量门禁）

    Args:
        raw_dir: raw/ 目录路径
        files: 可选的文件路径列表（相对于 raw_dir），传入时只加载指定文件
        auto_convert_flag: 是否自动转换非标准格式（默认 True，用于向后兼容）
    """
    if auto_convert_flag:
        docs = load_raw_documents(raw_dir, files=files)
        docs.extend(load_pdf_documents(raw_dir, files=files))
    else:
        docs = load_raw_documents_only(raw_dir, files=files)

    if not docs:
        return []

    # 质量门禁：过滤不合格文档
    from app.kg.quality_gate import validate_documents
    logger.info(f"质量检查：{len(docs)} 个文档")
    passed_docs, report = validate_documents(docs)
    logger.info(report.summary())

    return passed_docs
