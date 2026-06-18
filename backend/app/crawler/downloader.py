"""论文 PDF 下载与解析"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.crawler.scholar import PaperMetadata


def download_pdf(url: str, save_dir: str | None = None, filename: str | None = None) -> str | None:
    """下载 PDF 文件

    Args:
        url: PDF 下载链接
        save_dir: 保存目录，默认 raw/
        filename: 文件名，默认从 URL 提取

    Returns:
        保存的文件路径，失败返回 None
    """
    if not url:
        return None

    save_path = Path(save_dir or settings.raw_data_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    if filename is None:
        # 从 URL 提取文件名
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith(".pdf"):
            filename = f"paper_{hash(url) % 100000}.pdf"

    filepath = save_path / filename

    if filepath.exists():
        print(f"  文件已存在，跳过: {filepath.name}")
        return str(filepath)

    try:
        print(f"  正在下载: {url[:80]}...")
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

            # 检查是否是 PDF
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type and not response.content[:5] == b"%PDF-":
                print(f"  ⚠ 返回的内容不是 PDF（Content-Type: {content_type}）")
                return None

            filepath.write_bytes(response.content)
            print(f"  ✓ 下载成功: {filepath.name}（{len(response.content) / 1024:.1f} KB）")
            return str(filepath)

    except httpx.HTTPStatusError as e:
        print(f"  ✗ HTTP 错误 {e.response.status_code}: {url[:80]}")
    except Exception as e:
        print(f"  ✗ 下载失败: {e}")

    return None


def batch_download_pdfs(papers: list[PaperMetadata], save_dir: str | None = None) -> list[PaperMetadata]:
    """批量下载论文 PDF

    Args:
        papers: 论文元数据列表
        save_dir: 保存目录

    Returns:
        更新了 pdf_url 的论文列表
    """
    save_path = save_dir or settings.raw_data_dir
    downloaded = 0
    skipped = 0
    failed = 0

    papers_with_pdf = [p for p in papers if p.pdf_url]
    print(f"共 {len(papers_with_pdf)} 篇论文有 PDF 链接")

    for i, paper in enumerate(papers_with_pdf, 1):
        print(f"\n[{i}/{len(papers_with_pdf)}] {paper.title[:50]}...")

        # 生成有意义的文件名
        safe_title = re.sub(r'[^\w一-鿿\-]', '_', paper.title[:50]).strip('_')
        filename = f"{safe_title}.pdf"

        result = download_pdf(paper.pdf_url, save_path, filename)
        if result:
            downloaded += 1
        elif result is None and paper.pdf_url:
            failed += 1

        # 防止被封
        time.sleep(1)

    print(f"\n下载完成: 成功 {downloaded}，失败 {failed}")
    return papers


def parse_pdf(filepath: str) -> str:
    """解析 PDF 为纯文本

    Args:
        filepath: PDF 文件路径

    Returns:
        提取的文本内容
    """
    try:
        import pdfplumber
    except ImportError:
        print("错误：pdfplumber 未安装")
        return ""

    try:
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        content = "\n\n".join(text_parts)

        # 基础清理
        content = re.sub(r'\n{3,}', '\n\n', content)  # 多余空行
        content = re.sub(r' {2,}', ' ', content)       # 多余空格
        content = content.strip()

        return content

    except Exception as e:
        print(f"解析 PDF 失败 {filepath}: {e}")
        return ""


def parse_all_pdfs(raw_dir: str | None = None) -> dict[str, str]:
    """解析目录下所有 PDF 文件

    Args:
        raw_dir: PDF 目录，默认 raw/

    Returns:
        {文件路径: 提取的文本} 字典
    """
    raw_path = Path(raw_dir or settings.raw_data_dir)
    results = {}

    pdf_files = list(raw_path.glob("*.pdf"))
    print(f"找到 {len(pdf_files)} 个 PDF 文件")

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"  [{i}/{len(pdf_files)}] 解析: {pdf_path.name}")
        text = parse_pdf(str(pdf_path))
        if text:
            # 保存为同名 .txt
            txt_path = pdf_path.with_suffix(".txt")
            txt_path.write_text(text, encoding="utf-8")
            results[str(pdf_path)] = text
            print(f"    → 提取 {len(text)} 字，已保存: {txt_path.name}")
        else:
            print(f"    → 未提取到文本")

    return results
