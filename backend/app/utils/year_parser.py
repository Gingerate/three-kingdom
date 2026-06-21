"""年份解析工具 —— 将中文年号/自由文本年份转为公元整数

支持格式：
- 纯数字："200" → 200
- 年号+数字："建安五年" → 200
- 带"年"字："220年" → 220
- 约/大约前缀："约155" → 155
- 无法解析：返回 None
"""

from __future__ import annotations

import re

# 年号 → 起始公元年份映射（三国时期常用年号）
ERA_MAP: dict[str, int] = {
    # 东汉末年
    "中平": 184, "初平": 190, "兴平": 194, "建安": 196,
    "延康": 220,
    # 曹魏
    "黄初": 220, "太和": 227, "青龙": 233, "景初": 237,
    "正始": 240, "嘉平": 249, "正元": 254, "甘露": 256,
    "景元": 260, "咸熙": 264,
    # 蜀汉
    "章武": 221, "建兴": 223, "延熙": 238, "景耀": 258, "炎兴": 263,
    # 东吴
    "黄武": 222, "黄龙": 229, "嘉禾": 232, "赤乌": 238,
    "太元": 251, "神凤": 252, "建兴": 252, "五凤": 254,
    "太平": 256, "永安": 258, "元兴": 264, "甘露": 265,
    "宝鼎": 266, "建衡": 269, "凤凰": 272, "天册": 275,
    "天玺": 276, "天纪": 277,
    # 西晋
    "泰始": 265, "咸宁": 275, "太康": 280, "太熙": 290,
    # 其他常见
    "永元": 89, "永初": 107, "永宁": 120, "建光": 121,
    "延光": 122, "永建": 126, "阳嘉": 132, "永和": 136,
    "汉安": 142, "建康": 144, "永嘉": 145, "本初": 146,
    "和平": 150, "元嘉": 151, "永兴": 153, "永寿": 155,
    "延熹": 158, "永康": 167, "建宁": 168, "熹平": 172,
    "光和": 178, "中平": 184,
}

# 中文数字映射
CN_DIGITS: dict[str, int] = {
    "元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
    "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35,
    "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39, "四十": 40,
    "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45,
    "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49, "五十": 50,
    "五十一": 51, "五十二": 52, "五十三": 53, "五十四": 54, "五十五": 55,
    "五十六": 56, "五十七": 57, "五十八": 58, "五十九": 59, "六十": 60,
}


def _cn_to_int(s: str) -> int | None:
    """将中文数字转为整数"""
    s = s.strip()
    if s in CN_DIGITS:
        return CN_DIGITS[s]
    # 尝试阿拉伯数字
    try:
        return int(s)
    except ValueError:
        return None


def parse_year(text: str | None) -> int | None:
    """将年份文本转为公元整数

    Args:
        text: 年份文本，如 "200"、"建安五年"、"约155年"

    Returns:
        公元整数，无法解析返回 None
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    # 去除前缀
    text = re.sub(r'^(约|大约|公元前|公元|前)', '', text).strip()
    is_bce = '前' in text or 'bce' in text.lower()
    text = re.sub(r'(前|bce|BCE)', '', text, flags=re.IGNORECASE).strip()

    # 去除"年"字
    text = text.rstrip('年').strip()

    # 1. 纯阿拉伯数字
    m = re.match(r'^(\d+)$', text)
    if m:
        year = int(m.group(1))
        return -year if is_bce else year

    # 2. 年号 + 中文/阿拉伯数字：如 "建安五年"、"建安5年"
    m = re.match(r'^([^\d]+?)([\d元一二三四五六七八九十]+)$', text)
    if m:
        era_name = m.group(1).strip()
        year_num_str = m.group(2).strip()
        year_num = _cn_to_int(year_num_str)
        if year_num and era_name in ERA_MAP:
            return ERA_MAP[era_name] + year_num - 1

    # 3. 尝试所有已知年号前缀匹配
    for era_name, start_year in sorted(ERA_MAP.items(), key=lambda x: -len(x[0])):
        if text.startswith(era_name):
            rest = text[len(era_name):].strip()
            rest = rest.rstrip('年').strip()
            year_num = _cn_to_int(rest)
            if year_num:
                return start_year + year_num - 1

    # 4. 兜底：尝试提取文本中的数字
    m = re.search(r'(\d{1,4})', text)
    if m:
        year = int(m.group(1))
        if 1 <= year <= 999:
            return -year if is_bce else year

    return None


def parse_year_range(text: str | None) -> tuple[int | None, int | None]:
    """解析可能包含范围的年份文本

    如 "155-220" → (155, 220)
    如 "建安年间(196-220)" → (196, 220)
    """
    if not text:
        return None, None

    # 尝试匹配范围格式
    m = re.search(r'(\d{1,4})\s*[-~—–至到]\s*(\d{1,4})', text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # 单个年份
    year = parse_year(text)
    return year, year
