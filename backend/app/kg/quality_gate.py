"""格式转换质量门禁 —— 在分块前验证转换结果"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """验证结果级别"""
    PASS = "pass"        # 通过
    WARN = "warn"        # 警告（继续处理但标记）
    BLOCK = "block"      # 阻断（跳过该文档）


@dataclass
class ValidationResult:
    """验证结果"""
    level: ValidationLevel
    message: str
    details: list[str]

    @property
    def passed(self) -> bool:
        return self.level != ValidationLevel.BLOCK

    @property
    def has_warnings(self) -> bool:
        return self.level == ValidationLevel.WARN


@dataclass
class QualityReport:
    """质量检查报告"""
    total: int
    passed: int
    warned: int
    blocked: int
    results: list[tuple[str, ValidationResult]]  # (filename, result)

    def summary(self) -> str:
        lines = [
            f"质量检查完成：{self.total} 个文档",
            f"  ✓ 通过: {self.passed}",
            f"  ⚠ 警告: {self.warned}",
            f"  ✗ 阻断: {self.blocked}",
        ]
        if self.blocked > 0:
            lines.append("\n被阻断的文档:")
            for fname, result in self.results:
                if result.level == ValidationLevel.BLOCK:
                    lines.append(f"  - {fname}: {result.message}")
        return "\n".join(lines)


def validate_document(content: str, filename: str = "") -> ValidationResult:
    """验证单个文档的转换质量

    Args:
        content: 转换后的文本内容
        filename: 文件名（用于日志）

    Returns:
        ValidationResult 包含级别、消息和详细信息
    """
    details = []

    # ==================== 1. 空内容检查 ====================
    if not content or not content.strip():
        return ValidationResult(
            level=ValidationLevel.BLOCK,
            message="文档内容为空",
            details=["转换后未产生任何文本内容"],
        )

    # ==================== 2. 编码/乱码检测 ====================
    # 检查替换字符
    replacement_count = content.count('�')
    if replacement_count >= 3:
        return ValidationResult(
            level=ValidationLevel.BLOCK,
            message=f"检测到乱码（{replacement_count} 个替换字符）",
            details=["文档可能编码错误或损坏"],
        )

    # 检查不可打印字符占比
    # 排除常见的空白字符（空格、换行、制表符）
    printable_chars = re.sub(r'[\s\n\r\t]', '', content)
    if printable_chars:
        # 中文字符、英文字母、数字、常用标点都算有效字符
        valid_chars = re.sub(r'[^一-鿿　-〿a-zA-Z0-9\s\n\r\t.,;:!?\'"()（）【】《》、。，；：！？\-—…·]', '', printable_chars)
        non_printable_ratio = 1 - (len(valid_chars) / len(printable_chars))

        if non_printable_ratio > 0.15:  # 超过 15% 非有效字符
            return ValidationResult(
                level=ValidationLevel.BLOCK,
                message=f"无效字符占比过高（{non_printable_ratio:.0%}）",
                details=["文档可能包含大量乱码或二进制数据"],
            )

        if non_printable_ratio > 0.05:  # 超过 5% 发出警告
            details.append(f"无效字符占比 {non_printable_ratio:.1%}，建议检查")

    # ==================== 3. 内容完整性检查 ====================
    content_length = len(content.strip())

    # 最小长度阈值
    min_length = 100
    if content_length < min_length:
        return ValidationResult(
            level=ValidationLevel.BLOCK,
            message=f"内容过短（{content_length} 字符，最少 {min_length}）",
            details=["文档可能转换不完整"],
        )

    # 有效文字占比
    chinese_chars = len(re.findall(r'[一-鿿]', content))
    english_chars = len(re.findall(r'[a-zA-Z]', content))
    meaningful_length = chinese_chars + english_chars

    if content_length > 0:
        meaningful_ratio = meaningful_length / content_length
        if meaningful_ratio < 0.3:  # 有效文字不足 30%
            return ValidationResult(
                level=ValidationLevel.BLOCK,
                message=f"有效文字占比过低（{meaningful_ratio:.0%}）",
                details=["文档可能包含大量无意义内容"],
            )

        if meaningful_ratio < 0.5:  # 有效文字不足 50% 警告
            details.append(f"有效文字占比 {meaningful_ratio:.1%}，偏低")

    # ==================== 4. 结构检查 ====================
    # 检查是否有章节结构
    chapter_patterns = [
        r'^第[一二三四五六七八九十百零\d]+[回章节卷篇]',
        r'^[一-鿿]{1,6}(?:纪|传|志|列传)',
        r'^\d+\.\s+\S',
    ]

    has_chapters = False
    for pattern in chapter_patterns:
        if re.search(pattern, content, re.MULTILINE):
            has_chapters = True
            break

    if not has_chapters and content_length > 1000:
        details.append("未识别到章节结构，将作为整体处理")

    # 检查段落结构
    paragraphs = re.split(r'\n\s*\n|\n', content)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if len(paragraphs) < 2 and content_length > 500:
        details.append("段落结构不明显，可能需要检查换行符")

    # ==================== 5. 特殊问题检测 ====================
    # 检测重复内容（可能是转换错误）
    lines = content.split('\n')
    lines = [l.strip() for l in lines if l.strip()]
    if len(lines) > 10:
        unique_lines = set(lines)
        duplicate_ratio = 1 - (len(unique_lines) / len(lines))
        if duplicate_ratio > 0.5:  # 超过 50% 重复行
            return ValidationResult(
                level=ValidationLevel.BLOCK,
                message=f"重复内容过多（{duplicate_ratio:.0%}）",
                details=["文档可能转换错误导致内容重复"],
            )
        if duplicate_ratio > 0.3:
            details.append(f"重复内容占比 {duplicate_ratio:.1%}，偏高")

    # 检测常见转换错误标记
    # 注意：'???' 过于通用，正常文本中也可能出现（如乱码残留），不作为错误标记
    error_markers = ['[ERROR]', '[FAILED]', 'Conversion failed']
    for marker in error_markers:
        if marker.lower() in content.lower():
            return ValidationResult(
                level=ValidationLevel.BLOCK,
                message=f"检测到转换错误标记: {marker}",
                details=["格式转换过程中出现错误"],
            )

    # ==================== 最终判定 ====================
    if details:
        return ValidationResult(
            level=ValidationLevel.WARN,
            message="通过（有警告）",
            details=details,
        )

    return ValidationResult(
        level=ValidationLevel.PASS,
        message="通过",
        details=[],
    )


def validate_documents(documents: list, filename_key: str = "filename") -> tuple[list, QualityReport]:
    """批量验证文档，返回通过的文档列表和质量报告

    Args:
        documents: 文档列表（需要有 filename_key 指定的属性或字典键）
        filename_key: 获取文件名的键名

    Returns:
        (passed_documents, report): 通过的文档列表和质量报告
    """
    results = []
    passed_docs = []

    for doc in documents:
        # 获取文件名和内容
        if isinstance(doc, dict):
            filename = doc.get(filename_key, "unknown")
            content = doc.get("content", "")
        else:
            filename = getattr(doc, filename_key, "unknown")
            content = getattr(doc, "content", "")

        # 执行验证
        result = validate_document(content, filename)
        results.append((filename, result))

        # 根据结果决定是否通过
        if result.passed:
            passed_docs.append(doc)
            if result.has_warnings:
                logger.warning(f"  ⚠ {filename}: {'; '.join(result.details)}")
        else:
            logger.warning(f"  ✗ {filename}: {result.message}")

    # 统计
    report = QualityReport(
        total=len(documents),
        passed=sum(1 for _, r in results if r.level == ValidationLevel.PASS),
        warned=sum(1 for _, r in results if r.level == ValidationLevel.WARN),
        blocked=sum(1 for _, r in results if r.level == ValidationLevel.BLOCK),
        results=results,
    )

    return passed_docs, report
