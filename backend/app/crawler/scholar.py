"""Google Scholar 爬虫 —— 基于 scholarly 库的论文搜索"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from app.core.config import settings


@dataclass
class PaperMetadata:
    """论文元数据"""
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: str = ""
    url: str = ""
    pdf_url: str = ""
    citation_count: int = 0
    source: str = "Google Scholar"
    keyword: str = ""  # 搜索时使用的关键词
    journal: str = ""  # 期刊名


# ==================== 关键词策略（皇帝视角） ====================

KEYWORD_CATEGORIES = {
    "皇帝权力": [
        "东汉皇权",
        "汉代皇帝权力",
        "尚书台",
        "中朝官",
        "内朝外朝",
        "皇帝与权臣",
        "汉末皇权衰落",
        "挟天子以令诸侯",
    ],
    "诛灭权臣先例": [
        "汉和帝诛窦宪",
        "汉桓帝诛梁冀",
        "皇帝夺权",
        "少年皇帝",
        "外戚专权皇帝反击",
        "东汉皇帝除权臣",
        "汉代宫廷政变",
    ],
    "宫廷运作": [
        "东汉宫廷制度",
        "宦官权力东汉",
        "黄门侍郎",
        "中常侍",
        "侍中",
        "尚书台权力",
        "汉代中枢决策",
    ],
    "世家大族": [
        "东汉世家大族",
        "汝南袁氏",
        "弘农杨氏",
        "颍川荀氏",
        "汉末士族",
        "门阀士族起源",
        "世家与皇权",
        "党锢之祸",
        "清议",
    ],
    "军事": [
        "东汉禁军",
        "北军五校",
        "南军",
        "羽林军",
        "虎贲",
        "汉代兵制",
        "募兵制",
        "部曲",
        "董卓西凉军",
        "并州军",
        "汉末军事力量",
    ],
    "经济民生": [
        "东汉末年经济",
        "汉末土地兼并",
        "流民问题",
        "汉代赋税",
        "盐铁专营",
        "五铢钱",
        "黄巾起义原因",
        "东汉社会危机",
    ],
    "人物关系": [
        "王允诛董卓",
        "吕布丁原",
        "汉献帝东归",
        "李傕郭汜",
        "汉末群臣",
        "汉朝忠臣",
    ],
}


def get_all_keywords() -> list[str]:
    """获取所有关键词"""
    keywords = []
    for category, kws in KEYWORD_CATEGORIES.items():
        keywords.extend(kws)
    return keywords


def get_keywords_by_category(category: str) -> list[str]:
    """获取指定类别的关键词"""
    return KEYWORD_CATEGORIES.get(category, [])


# ==================== Google Scholar 搜索 ====================


def search_scholar(keyword: str, max_results: int = 10) -> list[PaperMetadata]:
    """搜索 Google Scholar

    Args:
        keyword: 搜索关键词
        max_results: 最大结果数

    Returns:
        论文元数据列表
    """
    try:
        from scholarly import scholarly
    except ImportError:
        print("错误：scholarly 未安装，请运行 pip install scholarly")
        return []

    papers = []
    try:
        search_results = scholarly.search_pubs(keyword)

        for i, result in enumerate(search_results):
            if i >= max_results:
                break

            bib = result.get("bib", {})
            paper = PaperMetadata(
                title=bib.get("title", ""),
                authors=bib.get("author", []) if isinstance(bib.get("author"), list) else [bib.get("author", "")],
                abstract=bib.get("abstract", ""),
                year=str(bib.get("pub_year", "")),
                url=result.get("pub_url", "") or result.get("eprint_url", ""),
                pdf_url=result.get("eprint_url", ""),
                citation_count=result.get("num_citations", 0),
                keyword=keyword,
                journal=bib.get("journal", "") or bib.get("venue", "") or bib.get("booktitle", ""),
            )
            papers.append(paper)

            # 防止被封 IP
            time.sleep(2)

    except Exception as e:
        print(f"搜索 '{keyword}' 时出错: {e}")

    return papers


def search_by_category(category: str, max_per_keyword: int = 5) -> list[PaperMetadata]:
    """按类别搜索论文

    Args:
        category: 类别名称（如"皇帝权力"）
        max_per_keyword: 每个关键词最大结果数

    Returns:
        去重后的论文列表
    """
    keywords = get_keywords_by_category(category)
    if not keywords:
        print(f"未知类别: {category}，可用类别: {list(KEYWORD_CATEGORIES.keys())}")
        return []

    all_papers: list[PaperMetadata] = []
    seen_titles: set[str] = set()

    print(f"正在搜索类别: {category}（{len(keywords)} 个关键词）")

    for i, kw in enumerate(keywords, 1):
        print(f"  [{i}/{len(keywords)}] 搜索: {kw}")
        papers = search_scholar(kw, max_results=max_per_keyword)

        for paper in papers:
            title_lower = paper.title.lower().strip()
            if title_lower and title_lower not in seen_titles:
                seen_titles.add(title_lower)
                all_papers.append(paper)

        print(f"    → 找到 {len(papers)} 篇，累计去重后 {len(all_papers)} 篇")

    return all_papers


def search_all_categories(max_per_keyword: int = 3) -> list[PaperMetadata]:
    """搜索所有类别的论文

    Args:
        max_per_keyword: 每个关键词最大结果数

    Returns:
        所有类别的论文列表
    """
    all_papers: list[PaperMetadata] = []
    seen_titles: set[str] = set()

    categories = list(KEYWORD_CATEGORIES.keys())
    for i, category in enumerate(categories, 1):
        print(f"\n{'='*50}")
        print(f"类别 [{i}/{len(categories)}]: {category}")
        papers = search_by_category(category, max_per_keyword=max_per_keyword)

        for paper in papers:
            title_lower = paper.title.lower().strip()
            if title_lower and title_lower not in seen_titles:
                seen_titles.add(title_lower)
                all_papers.append(paper)

    print(f"\n{'='*50}")
    print(f"搜索完成，共找到 {len(all_papers)} 篇不重复论文")

    return all_papers


# ==================== 结果保存 ====================


def save_search_results(papers: list[PaperMetadata], output_path: str | None = None) -> str:
    """保存搜索结果到 JSON 文件"""
    if output_path is None:
        output_path = str(
            Path(settings.raw_data_dir).parent / "processed" / "scholar_results.json"
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    data = [asdict(p) for p in papers]
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已保存 {len(papers)} 篇论文信息到: {output}")
    return str(output)


def load_search_results(input_path: str) -> list[PaperMetadata]:
    """从 JSON 文件加载搜索结果"""
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    return [PaperMetadata(**item) for item in data]
