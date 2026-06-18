"""语料导入模块 —— 读取 raw/ 目录下的文本文件，解析元数据

支持自动转换：.docx/.html/.rtf/.odt/.epub 等格式会自动转为 .md 后再处理
"""

import os
from pathlib import Path
from dataclasses import dataclass

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

    if "三国志" in name or "sgz" in name:
        return "三国志", "正史"
    elif "三国演义" in name or "sgyy" in name or "演义" in name:
        return "三国演义", "演义"
    elif "后汉书" in name:
        return "后汉书", "正史"
    elif "资治通鉴" in name:
        return "资治通鉴", "正史"
    elif "论文" in name or "paper" in name:
        return f"论文_{filename}", "论文"
    else:
        return filename, "其他"


def auto_convert(raw_dir: Path) -> int:
    """自动将 raw/ 目录下非标准文本格式转为 .md

    Returns:
        成功转换的文件数
    """
    from app.tools.translator import convert_to_md, SUPPORTED_EXTENSIONS

    converted = 0
    for filepath in sorted(raw_dir.rglob("*")):
        if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
            result = convert_to_md(str(filepath), str(raw_dir))
            if result.success:
                converted += 1
                print(f"  ✓ {result.message}")
                if result.issues:
                    for issue in result.issues:
                        print(f"    ⚠ {issue}")
            else:
                print(f"  ✗ {result.message}")

    return converted


def load_raw_documents(raw_dir: str | None = None) -> list[RawDocument]:
    """加载 raw/ 目录下所有文本文件（含自动格式转换）"""
    raw_path = Path(raw_dir or settings.raw_data_dir)
    if not raw_path.exists():
        raw_path.mkdir(parents=True, exist_ok=True)
        return []

    # 先自动转换非标准格式
    from app.tools.translator import SUPPORTED_EXTENSIONS
    has_convertible = any(
        f.suffix.lower() in SUPPORTED_EXTENSIONS
        for f in raw_path.rglob("*") if f.is_file()
    )
    if has_convertible:
        print("检测到非标准格式文件，自动转换中...")
        auto_convert(raw_path)

    # 加载所有可读文本文件
    documents = []
    supported_ext = {".txt", ".md", ".text"}

    for filepath in sorted(raw_path.rglob("*")):
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
                print(f"警告：无法读取文件 {filepath}: {e}")

    return documents


def load_pdf_documents(raw_dir: str | None = None) -> list[RawDocument]:
    """加载 raw/ 目录下的 PDF 文件（学术论文）"""
    try:
        import pdfplumber
    except ImportError:
        print("警告：pdfplumber 未安装，跳过 PDF 文件")
        return []

    raw_path = Path(raw_dir or settings.raw_data_dir)
    documents = []

    for filepath in sorted(raw_path.rglob("*.pdf")):
        try:
            with pdfplumber.open(filepath) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                content = "\n\n".join(text_parts)
                if not content.strip():
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
            print(f"警告：无法解析 PDF {filepath}: {e}")

    return documents


def load_all_documents(raw_dir: str | None = None) -> list[RawDocument]:
    """加载所有文档（文本 + PDF，自动转换非标准格式，含质量门禁）"""
    docs = load_raw_documents(raw_dir)
    docs.extend(load_pdf_documents(raw_dir))

    if not docs:
        return []

    # 质量门禁：过滤不合格文档
    from app.kg.quality_gate import validate_documents
    print(f"\n质量检查：{len(docs)} 个文档")
    passed_docs, report = validate_documents(docs)
    print(report.summary())

    return passed_docs
