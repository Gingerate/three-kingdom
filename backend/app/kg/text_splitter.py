"""文本切分模块 —— 混合策略：章节粗切 → 段落细切（支持 Agentic 语义分块）"""

import re
import json
from dataclasses import dataclass, field

from app.core.config import settings


def get_llm():
    """延迟导入 LLM"""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.1,
        max_tokens=2048,
    )


@dataclass
class Chunk:
    """切分后的文本块"""
    content: str
    source: str          # 实际文件路径（相对于 raw/）
    source_name: str     # 语义标识（如 "三国志", "三国演义"）
    category: str        # 分类（正史/演义/论文）
    chapter: str         # 章节标识（如"第一回"、"武帝纪"）
    chunk_index: int     # 在该章节内的序号
    metadata: dict       # 其他元数据


# 章节匹配模式
CHAPTER_PATTERNS = [
    # 三国演义：第一回、第二回...
    re.compile(r'^第[一二三四五六七八九十百零\d]+回', re.MULTILINE),
    # 三国志：XX纪、XX传、XX志
    re.compile(r'^[一-鿿]{1,6}(?:纪|传|志|列传)', re.MULTILINE),
    # 通用：以数字或中文数字开头的标题行
    re.compile(r'^(?:第[一二三四五六七八九十百零\d]+[章节卷篇]|[一二三四五六七八九十\d]+[、.])', re.MULTILINE),
    # 论文：1. / 2. 等章节号
    re.compile(r'^\d+\.\s+\S', re.MULTILINE),
]


def split_by_chapters(text: str) -> list[tuple[str, str]]:
    """粗切：按章节标题切分，返回 [(chapter_name, content), ...]"""

    # 尝试找到所有章节标题的位置
    chapter_positions: list[tuple[int, str]] = []

    for pattern in CHAPTER_PATTERNS:
        for match in pattern.finditer(text):
            chapter_positions.append((match.start(), match.group().strip()))

    if not chapter_positions:
        # 没有找到章节标题，整体作为一个章节
        return [("未分章", text)]

    # 按位置排序，去重
    chapter_positions.sort(key=lambda x: x[0])

    # 切分文本
    chapters = []
    for i, (pos, title) in enumerate(chapter_positions):
        end_pos = chapter_positions[i + 1][0] if i + 1 < len(chapter_positions) else len(text)
        content = text[pos:end_pos].strip()
        if content:
            chapters.append((title, content))

    # 如果第一个章节之前有内容（前言/序），加到前面
    if chapter_positions[0][0] > 0:
        prefix = text[:chapter_positions[0][0]].strip()
        if prefix:
            chapters.insert(0, ("前言", prefix))

    return chapters


def split_by_paragraphs(text: str, chunk_size: int | None = None,
                        chunk_overlap: int | None = None) -> list[str]:
    """细切：按段落切分，带滑动窗口 overlap"""

    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap

    # 安全检查：overlap 必须小于 chunk_size，否则滑动窗口会无限循环
    if overlap >= size:
        overlap = max(0, size // 4)

    # 先按段落（空行/换行）切分
    paragraphs = re.split(r'\n\s*\n|\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # 如果单个段落就超过 chunk_size，单独切分
        if len(para) > size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            # 对长段落做滑动窗口切分
            start = 0
            while start < len(para):
                end = start + size
                chunk = para[start:end]
                if chunk:
                    chunks.append(chunk)
                start = end - overlap
            continue

        # 尝试合并段落
        if len(current_chunk) + len(para) + 1 <= size:
            current_chunk = f"{current_chunk}\n{para}" if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # 新 chunk 带 overlap（取上一个 chunk 的尾部）
            if overlap > 0 and chunks:
                tail = chunks[-1][-overlap:]
                current_chunk = f"{tail}\n{para}"
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def split_document(content: str, source: str, category: str,
                   source_name: str = "") -> list[Chunk]:
    """完整切分流程：章节粗切 → 段落细切

    根据配置自动选择传统分块或 Agentic 语义分块
    """
    if settings.agentic_split:
        return split_document_agentic(content, source, category, source_name)
    return split_document_basic(content, source, category, source_name)


def split_document_basic(content: str, source: str, category: str,
                         source_name: str = "") -> list[Chunk]:
    """传统分块流程：章节粗切 → 段落细切"""

    chapters = split_by_chapters(content)
    all_chunks = []
    global_index = 0

    for chapter_name, chapter_text in chapters:
        paragraphs = split_by_paragraphs(chapter_text)

        for i, para in enumerate(paragraphs):
            all_chunks.append(Chunk(
                content=para,
                source=source,
                source_name=source_name,
                category=category,
                chapter=chapter_name,
                chunk_index=i,
                metadata={
                    "global_index": global_index,
                    "char_count": len(para),
                },
            ))
            global_index += 1

    return all_chunks


# ==================== Agentic 语义分块 ====================


def llm_analyze_chapter(chapter_text: str, chapter_name: str) -> dict:
    """LLM 分析章节，返回语义边界和摘要

    Returns:
        {
            "boundaries": [int],  # 语义段落边界位置列表
            "summary": str,       # 章节摘要
            "content_type": str   # 内容类型：narrative/argument/dialogue/mixed
        }
    """
    llm = get_llm()

    # 如果章节太长，截取前 3000 字分析
    analyze_text = chapter_text[:3000] if len(chapter_text) > 3000 else chapter_text

    prompt = f"""分析以下历史文本章节，识别语义段落边界。

章节名称：{chapter_name}
章节内容：
{analyze_text}

请输出 JSON 格式：
{{
    "boundaries": [位置1, 位置2, ...],  // 语义段落的起始位置（字符索引）
    "summary": "50字以内的章节摘要",
    "content_type": "narrative/argument/dialogue/mixed"  // 叙事/论述/对话/混合
}}

语义段落边界规则：
1. 话题转换处（从讨论A转到讨论B）
2. 论点分界处（不同论据或例子之间）
3. 叙事节奏变化处（从概述转为细节）
4. 不要在句子中间断开"""

    from langchain_core.messages import SystemMessage, HumanMessage

    response = llm.invoke([
        SystemMessage(content="你是历史文本分析专家，擅长识别文本的语义结构。"),
        HumanMessage(content=prompt),
    ])

    try:
        text = response.content.strip()
        # 提取 JSON（修复：第二次搜索需从第一个 ``` 之后开始）
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        result = json.loads(text)
        return {
            "boundaries": result.get("boundaries", []),
            "summary": result.get("summary", ""),
            "content_type": result.get("content_type", "mixed"),
        }
    except (json.JSONDecodeError, ValueError):
        return {"boundaries": [], "summary": "", "content_type": "mixed"}


def get_adaptive_chunk_size(content_type: str) -> tuple[int, int]:
    """根据内容类型返回自适应的 chunk_size 和 overlap

    Returns:
        (chunk_size, chunk_overlap)
    """
    size_map = {
        "narrative": (600, 80),    # 叙事段落：大块，保持故事连贯
        "argument": (300, 50),     # 论据密集：小块，精确检索
        "dialogue": (400, 60),     # 对话：中等，保持对话完整
        "mixed": (400, 50),        # 混合：默认值
    }
    return size_map.get(content_type, (settings.chunk_size, settings.chunk_overlap))


def split_by_semantic_boundaries(text: str, boundaries: list[int],
                                  chunk_size: int, chunk_overlap: int) -> list[str]:
    """根据语义边界切分文本"""

    if not boundaries:
        return split_by_paragraphs(text, chunk_size, chunk_overlap)

    # 按边界切分
    segments = []
    prev_pos = 0

    for pos in sorted(boundaries):
        if pos <= prev_pos or pos >= len(text):
            continue
        segment = text[prev_pos:pos].strip()
        if segment:
            segments.append(segment)
        prev_pos = pos

    # 添加最后一段
    remaining = text[prev_pos:].strip()
    if remaining:
        segments.append(remaining)

    # 对每个段落按大小进一步切分
    chunks = []
    for segment in segments:
        if len(segment) > chunk_size * 1.5:
            # 段落太大，用滑动窗口切分
            sub_chunks = split_by_paragraphs(segment, chunk_size, chunk_overlap)
            chunks.extend(sub_chunks)
        else:
            chunks.append(segment)

    return chunks


def llm_validate_and_merge(chunks: list[str]) -> list[str]:
    """LLM 验证分块质量，合并不完整的块"""

    if len(chunks) <= 1:
        return chunks

    llm = get_llm()

    # 检查前几个块的边界质量
    check_count = min(5, len(chunks) - 1)  # 边界数 = 块数 - 1
    if check_count <= 0:
        return chunks

    samples = []
    for i in range(check_count):
        # 取每个块的最后 80 字和下一个块的前 80 字
        end = chunks[i][-80:] if len(chunks[i]) > 80 else chunks[i]
        start = chunks[i + 1][:80] if i + 1 < len(chunks) else ""
        samples.append(f"块{i}结尾: ...{end}\n块{i+1}开头: {start}...")

    prompt = f"""检查以下文本分块的边界是否合理（是否在句子中间断开）：

{chr(10).join(samples)}

对每个边界，输出 JSON 数组，true 表示边界合理，false 表示需要合并：
[true, false, true, ...]

只输出 JSON 数组，不要其他内容。"""

    from langchain_core.messages import SystemMessage, HumanMessage

    try:
        response = llm.invoke([
            SystemMessage(content="你是文本分块质量检查专家。"),
            HumanMessage(content=prompt),
        ])

        text = response.content.strip()
        if "```" in text:
            text = text[text.index("```") + 3:text.rindex("```")].strip()

        validations = json.loads(text)

        # 根据验证结果合并（从后往前合并，避免索引偏移问题）
        merged = list(chunks)
        for i in range(min(len(validations), check_count) - 1, -1, -1):
            if not validations[i] and i + 1 < len(merged):
                # 合并块 i 和块 i+1
                merged[i] = merged[i] + "\n" + merged[i + 1]
                merged[i + 1] = ""

        return [c for c in merged if c]

    except (json.JSONDecodeError, ValueError, Exception):
        # 验证失败，返回原块
        return chunks


def split_document_agentic(content: str, source: str, category: str,
                           source_name: str = "") -> list[Chunk]:
    """Agentic 语义分块流程：章节粗切 → LLM 分析 → 自适应分块 → 上下文增强"""

    from langchain_core.messages import SystemMessage, HumanMessage

    chapters = split_by_chapters(content)
    all_chunks = []
    global_index = 0

    for chapter_name, chapter_text in chapters:
        # 1. LLM 分析章节
        analysis = llm_analyze_chapter(chapter_text, chapter_name)
        chapter_summary = analysis["summary"]
        content_type = analysis["content_type"]

        # 2. 自适应分块大小
        chunk_size, chunk_overlap = get_adaptive_chunk_size(content_type)

        # 3. 根据语义边界切分
        semantic_chunks = split_by_semantic_boundaries(
            chapter_text, analysis["boundaries"], chunk_size, chunk_overlap
        )

        # 4. LLM 验证分块质量
        validated_chunks = llm_validate_and_merge(semantic_chunks)

        # 5. 构建 Chunk 对象，附加上下文摘要
        for i, para in enumerate(validated_chunks):
            # 上下文增强：在 metadata 中添加章节摘要
            context_prefix = f"[{chapter_name}] {chapter_summary}" if chapter_summary else ""

            all_chunks.append(Chunk(
                content=para,
                source=source,
                source_name=source_name,
                category=category,
                chapter=chapter_name,
                chunk_index=i,
                metadata={
                    "global_index": global_index,
                    "char_count": len(para),
                    "chapter_summary": chapter_summary,
                    "content_type": content_type,
                    "context": context_prefix,
                },
            ))
            global_index += 1

    return all_chunks
