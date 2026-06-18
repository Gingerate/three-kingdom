"""解析工具函数"""

import json
from typing import Any


def parse_llm_json(text: str, default: Any = None) -> dict | list | None:
    """解析 LLM 返回的 JSON 文本，自动处理 markdown 代码块包裹

    Args:
        text: LLM 返回的原始文本
        default: 解析失败时的默认值

    Returns:
        解析后的 dict/list，失败返回 default
    """
    if not text:
        return default

    text = text.strip()

    # 处理 ```json ... ``` 包裹
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return default
