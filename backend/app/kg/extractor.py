"""LLM 知识抽取模块 —— 从文本中提取实体和关系三元组"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings


# ==================== 数据结构 ====================


@dataclass
class ExtractedEntity:
    """抽取的实体"""
    name: str
    entity_type: str  # person / event / force
    description: str = ""
    courtesy_name: str = ""  # 人物：字
    origin: str = ""         # 人物：籍贯
    birth_year: str = ""     # 人物：生年
    death_year: str = ""     # 人物：卒年
    year: str = ""           # 事件：发生年份
    location: str = ""       # 事件：地点
    leader: str = ""         # 势力：领袖
    period: str = ""         # 势力：存续时期


@dataclass
class ExtractedRelation:
    """抽取的关系"""
    source_name: str
    source_type: str  # person / event / force
    target_name: str
    target_type: str  # person / event / force
    relation_type: str  # belongs_to / participated / ally / rival / holds_office
    description: str = ""


@dataclass
class ExtractionResult:
    """抽取结果"""
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    source_text: str = ""
    raw_response: str = ""


# ==================== Prompt 模板 ====================

SYSTEM_PROMPT = """你是一个专业的历史知识抽取助手。你的任务是从给定的历史文本中提取结构化的知识三元组。

你需要提取以下三类实体和它们之间的关系：

## 实体类型

### 1. 人物 (person)
- name: 人物姓名（必填）
- courtesy_name: 字（如有的话）
- origin: 籍贯/出生地
- birth_year: 出生年份
- death_year: 去世年份
- description: 一句话描述此人

### 2. 事件 (event)
- name: 事件名称（必填）
- year: 发生年份（尽量用公元纪年，如"200"；若原文为年号则保留，如"建安五年"）
- location: 发生地点
- description: 一句话描述此事件

### 3. 势力 (force)
- name: 势力名称（必填）
- leader: 领袖/首领
- period: 存续时期
- description: 一句话描述此势力

## 关系类型
- belongs_to: 人物隶属于某势力
- participated: 人物参与了某事件
- ally: 人物/势力之间是盟友关系
- rival: 人物/势力之间是对立关系
- holds_office: 人物担任某官职（此时 target 用 person 类型，name 写官职名）
- leads: 人物领导某势力
- caused: 事件导致了另一事件
- located_at: 事件发生在某地点

## 输出格式
严格输出以下 JSON 格式，不要输出任何其他内容：

```json
{
  "entities": [
    {
      "name": "曹操",
      "entity_type": "person",
      "description": "东汉末年权臣，魏国奠基者",
      "courtesy_name": "孟德",
      "origin": "沛国谯县",
      "birth_year": "155",
      "death_year": "220"
    }
  ],
  "relations": [
    {
      "source_name": "曹操",
      "source_type": "person",
      "target_name": "官渡之战",
      "target_type": "event",
      "relation_type": "participated",
      "description": "曹操在官渡之战中击败袁绍"
    }
  ]
}
```

## 注意事项
1. 只提取文本中明确提到的信息，不要推测
2. 如果某个属性在文本中没有提及，留空字符串
3. 人名使用最常见的称呼（如"诸葛亮"而非"孔明"，除非文本中只出现了"孔明"）
4. 关系要有实际意义，不要提取过于泛泛的关系
5. 如果文本中没有可提取的实体或关系，返回空的 entities 和 relations 数组"""


def build_extraction_prompt(text: str) -> str:
    """构建抽取 prompt"""
    return f"""请从以下历史文本中提取实体和关系：

---
{text}
---

请严格按照系统提示中的 JSON 格式输出。"""


# ==================== 抽取器 ====================


def get_llm() -> ChatOpenAI:
    """获取 LLM 实例"""
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.1,  # 低温度，保证抽取稳定性
        max_tokens=4096,
    )


def parse_extraction_response(response_text: str) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
    """解析 LLM 返回的 JSON"""
    # 尝试提取 JSON 块
    text = response_text.strip()

    # 处理 ```json ... ``` 包裹的情况
    try:
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()
    except ValueError:
        # 找不到闭合的 ```，降级使用原始文本
        pass

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试修复常见的 JSON 问题
        # 移除尾部逗号
        import re
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [], []

    entities = []
    for item in data.get("entities", []):
        entities.append(ExtractedEntity(
            name=item.get("name", ""),
            entity_type=item.get("entity_type", ""),
            description=item.get("description", ""),
            courtesy_name=item.get("courtesy_name", ""),
            origin=item.get("origin", ""),
            birth_year=item.get("birth_year", ""),
            death_year=item.get("death_year", ""),
            year=item.get("year", ""),
            location=item.get("location", ""),
            leader=item.get("leader", ""),
            period=item.get("period", ""),
        ))

    relations = []
    for item in data.get("relations", []):
        relations.append(ExtractedRelation(
            source_name=item.get("source_name", ""),
            source_type=item.get("source_type", ""),
            target_name=item.get("target_name", ""),
            target_type=item.get("target_type", ""),
            relation_type=item.get("relation_type", ""),
            description=item.get("description", ""),
        ))

    return entities, relations


def extract_from_text(text: str, source: str = "") -> ExtractionResult:
    """从单段文本中抽取实体和关系

    Args:
        text: 输入文本
        source: 来源标识

    Returns:
        ExtractionResult
    """
    llm = get_llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_extraction_prompt(text)),
    ]

    response = llm.invoke(messages)
    entities, relations = parse_extraction_response(response.content)

    return ExtractionResult(
        entities=entities,
        relations=relations,
        source_text=text,
        raw_response=response.content,
    )


def extract_from_chunks(chunks: list, batch_size: int = 5) -> list[ExtractionResult]:
    """批量从文本块中抽取实体和关系

    Args:
        chunks: Chunk 对象列表（来自 text_splitter）
        batch_size: 每批处理的 chunk 数量（合并相邻 chunk 以获取更完整的上下文）

    Returns:
        抽取结果列表
    """
    results = []

    # 按来源和章节分组
    grouped: dict[str, list] = {}
    for chunk in chunks:
        key = f"{chunk.source}:{chunk.chapter}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(chunk)

    # 将分组按 batch_size 分批
    group_items = list(grouped.items())
    batches = []
    for i in range(0, len(group_items), batch_size):
        batches.append(group_items[i:i + batch_size])

    total_batches = len(batches)
    for batch_idx, batch in enumerate(batches, 1):
        # 合并本批次所有 chunk 的文本
        combined_texts = []
        source = ""
        for key, group_chunks in batch:
            combined_texts.append("\n\n".join(c.content for c in group_chunks))
            if not source and group_chunks:
                source = group_chunks[0].source

        combined_text = "\n\n---\n\n".join(combined_texts)

        # 如果合并后文本太长，截断（LLM 上下文限制）
        if len(combined_text) > 8000:
            combined_text = combined_text[:8000]

        print(f"  [批次 {batch_idx}/{total_batches}] 正在抽取 ({len(combined_text)} 字)")

        try:
            result = extract_from_text(combined_text, source)
            results.append(result)
            print(f"    → 提取到 {len(result.entities)} 个实体，{len(result.relations)} 个关系")
        except Exception as e:
            print(f"    ✗ 抽取失败: {e}")
            results.append(ExtractionResult(source_text=combined_text))

    return results
