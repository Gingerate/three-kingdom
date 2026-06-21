"""RAG 评测脚本 —— 运行基准问答对，计算 Faithfulness / Relevance / Source Recall / Key Point Coverage

用法：
    cd backend
    python -m eval.run_eval                    # 运行全部
    python -m eval.run_eval --category factual # 只运行事实型
    python -m eval.run_eval --limit 5          # 只运行前 5 题
    python -m eval.run_eval --output report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 确保 backend/ 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402


# ==================== 数据结构 ====================

@dataclass
class EvalQuestion:
    id: int
    category: str
    question: str
    expected_answer: str | None = None
    expected_sources: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    id: int
    category: str
    question: str
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    route: str = ""
    sub_questions: list[str] = field(default_factory=list)
    # 指标
    faithfulness: float = 0.0      # 0-1：引用来源是否真实存在于检索结果中
    relevance: float = 0.0         # 1-5：回答是否切题（LLM 自评）
    source_recall: float = 0.0     # 0-1：expected_sources 被检索到的比例
    key_point_coverage: float = 0.0  # 0-1：key_points 在回答中出现的比例
    # 元数据
    elapsed_seconds: float = 0.0
    error: str | None = None


@dataclass
class EvalReport:
    timestamp: str
    total_questions: int
    completed: int
    failed: int
    elapsed_seconds: float
    # 汇总指标
    avg_faithfulness: float = 0.0
    avg_relevance: float = 0.0
    avg_source_recall: float = 0.0
    avg_key_point_coverage: float = 0.0
    # 分类指标
    category_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    # 逐题结果
    results: list[EvalResult] = field(default_factory=list)


# ==================== 评测逻辑 ====================

def load_benchmark(path: str | None = None) -> list[EvalQuestion]:
    """加载评测数据集"""
    benchmark_path = Path(path or Path(__file__).parent / "benchmark.json")
    with open(benchmark_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = []
    for q in data["questions"]:
        questions.append(EvalQuestion(
            id=q["id"],
            category=q["category"],
            question=q["question"],
            expected_answer=q.get("expected_answer"),
            expected_sources=q.get("expected_sources", []),
            key_points=q.get("key_points", []),
        ))
    return questions


def run_single_eval(question: EvalQuestion) -> EvalResult:
    """运行单个评测问题"""
    from app.rag.agent import run_rag, extract_sources_from_answer

    result = EvalResult(id=question.id, category=question.category, question=question.question)
    start = time.time()

    try:
        rag_output = run_rag(question.question, session_id=None)
        result.answer = rag_output.get("answer", "")
        result.sources = rag_output.get("sources", [])
        result.route = rag_output.get("route", "")
        result.sub_questions = rag_output.get("sub_questions", [])

        # 1. Faithfulness：回答中引用的来源是否存在于检索结果中
        cited_sources = extract_sources_from_answer(result.answer)
        if cited_sources:
            matched = sum(1 for s in cited_sources if any(s in src or src in s for src in result.sources))
            result.faithfulness = matched / len(cited_sources)
        else:
            result.faithfulness = 1.0  # 没有引用来源，视为忠实（不扣分）

        # 2. Source Recall：expected_sources 中有多少被检索到
        if question.expected_sources:
            found = sum(
                1 for expected in question.expected_sources
                if any(expected in src or src in expected for src in result.sources)
            )
            result.source_recall = found / len(question.expected_sources)
        else:
            result.source_recall = 1.0

        # 3. Key Point Coverage：key_points 在回答中出现的比例
        if question.key_points:
            answer_lower = result.answer.lower()
            found_points = sum(
                1 for point in question.key_points
                if point.lower() in answer_lower
            )
            result.key_point_coverage = found_points / len(question.key_points)
        else:
            result.key_point_coverage = 1.0

        # 4. Relevance：LLM 自评（1-5 分）
        result.relevance = _llm_relevance_score(question.question, result.answer)

    except Exception as e:
        result.error = str(e)

    result.elapsed_seconds = time.time() - start
    return result


def _llm_relevance_score(question: str, answer: str) -> float:
    """用 LLM 评估回答相关性（1-5 分）"""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
            max_tokens=10,
        )

        prompt = f"""请评估以下回答对问题的相关性，只输出 1-5 的数字（5=完全相关，1=完全不相关）。

问题：{question}
回答：{answer[:500]}

评分："""

        response = llm.invoke([HumanMessage(content=prompt)])
        score_text = response.content.strip()
        # 提取数字
        import re
        m = re.search(r'(\d)', score_text)
        if m:
            score = int(m.group(1))
            return max(1.0, min(5.0, float(score)))
        return 3.0  # 默认中等分数
    except Exception:
        return 3.0  # LLM 评分失败时给默认分


# ==================== 报告生成 ====================

def generate_report(results: list[EvalResult], elapsed: float) -> EvalReport:
    """生成评测报告"""
    from datetime import datetime

    completed = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]

    report = EvalReport(
        timestamp=datetime.now().isoformat(),
        total_questions=len(results),
        completed=len(completed),
        failed=len(failed),
        elapsed_seconds=round(elapsed, 1),
    )

    if completed:
        report.avg_faithfulness = round(sum(r.faithfulness for r in completed) / len(completed), 3)
        report.avg_relevance = round(sum(r.relevance for r in completed) / len(completed), 2)
        report.avg_source_recall = round(sum(r.source_recall for r in completed) / len(completed), 3)
        report.avg_key_point_coverage = round(sum(r.key_point_coverage for r in completed) / len(completed), 3)

    # 分类指标
    categories = set(r.category for r in results)
    for cat in categories:
        cat_results = [r for r in completed if r.category == cat]
        if cat_results:
            report.category_metrics[cat] = {
                "count": len(cat_results),
                "faithfulness": round(sum(r.faithfulness for r in cat_results) / len(cat_results), 3),
                "relevance": round(sum(r.relevance for r in cat_results) / len(cat_results), 2),
                "source_recall": round(sum(r.source_recall for r in cat_results) / len(cat_results), 3),
                "key_point_coverage": round(sum(r.key_point_coverage for r in cat_results) / len(cat_results), 3),
            }

    report.results = results
    return report


def print_summary(report: EvalReport):
    """终端打印评测汇总"""
    print("\n" + "=" * 60)
    print("  三国知识库 RAG 评测报告")
    print("=" * 60)
    print(f"  时间: {report.timestamp}")
    print(f"  题目: {report.total_questions} 道（完成 {report.completed}，失败 {report.failed}）")
    print(f"  耗时: {report.elapsed_seconds} 秒")
    print("-" * 60)
    print("  汇总指标:")
    print(f"    Faithfulness（忠实度）:      {report.avg_faithfulness:.1%}")
    print(f"    Relevance（相关度）:         {report.avg_relevance:.2f} / 5")
    print(f"    Source Recall（来源召回）:    {report.avg_source_recall:.1%}")
    print(f"    Key Point Coverage（要点覆盖）: {report.avg_key_point_coverage:.1%}")

    if report.category_metrics:
        print("-" * 60)
        print("  分类指标:")
        for cat, metrics in report.category_metrics.items():
            print(f"    [{cat}] ({metrics['count']} 题)")
            print(f"      忠实度: {metrics['faithfulness']:.1%}  相关度: {metrics['relevance']:.2f}")
            print(f"      来源召回: {metrics['source_recall']:.1%}  要点覆盖: {metrics['key_point_coverage']:.1%}")

    if report.failed > 0:
        print("-" * 60)
        print("  失败题目:")
        for r in report.results:
            if r.error:
                print(f"    #{r.id} [{r.category}] {r.question[:40]}... → {r.error[:60]}")

    print("=" * 60)


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="三国知识库 RAG 评测")
    parser.add_argument("--benchmark", type=str, help="评测数据集路径")
    parser.add_argument("--category", type=str, help="只评测指定类别: factual/analytical/comparative")
    parser.add_argument("--limit", type=int, help="只运行前 N 题")
    parser.add_argument("--output", type=str, help="输出 JSON 报告路径")
    args = parser.parse_args()

    # 加载数据集
    questions = load_benchmark(args.benchmark)
    if args.category:
        questions = [q for q in questions if q.category == args.category]
    if args.limit:
        questions = questions[:args.limit]

    print(f"开始评测：{len(questions)} 道题目")
    print(f"LLM 模型：{settings.llm_model}")
    print()

    results = []
    start_time = time.time()

    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] [{q.category}] {q.question[:50]}...", end=" ", flush=True)
        result = run_single_eval(q)
        results.append(result)

        if result.error:
            print(f"✗ 错误: {result.error[:40]}")
        else:
            print(f"✓ {result.elapsed_seconds:.1f}s  "
                  f"F={result.faithfulness:.0%} R={result.relevance:.1f} "
                  f"SR={result.source_recall:.0%} KP={result.key_point_coverage:.0%}")

    elapsed = time.time() - start_time
    report = generate_report(results, elapsed)

    # 打印汇总
    print_summary(report)

    # 保存 JSON 报告
    output_path = args.output or str(Path(__file__).parent / "report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {output_path}")

    return report


if __name__ == "__main__":
    main()
