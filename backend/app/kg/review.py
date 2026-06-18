"""抽取结果审核模块 —— 人工审核/修正后写入 SQLite"""

from __future__ import annotations

from dataclasses import dataclass

from app.kg.extractor import ExtractionResult, ExtractedEntity, ExtractedRelation
from app.models.crud import (
    create_person, create_event, create_force, create_relation,
)
from app.core.database import init_db


@dataclass
class ReviewItem:
    """待审核的抽取结果"""
    id: int
    source_text: str
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]
    status: str = "pending"  # pending / approved / rejected


# 内存中的待审核队列（实际项目可持久化到 Redis/DB）
_review_queue: list[ReviewItem] = []
_next_id = 1


def add_to_review_queue(result: ExtractionResult) -> int:
    """将抽取结果加入待审核队列

    Returns:
        审核项 ID
    """
    global _next_id
    item = ReviewItem(
        id=_next_id,
        source_text=result.source_text,
        entities=result.entities,
        relations=result.relations,
    )
    _review_queue.append(item)
    _next_id += 1
    return item.id


def add_batch_to_review_queue(results: list[ExtractionResult]) -> list[int]:
    """批量加入审核队列"""
    return [add_to_review_queue(r) for r in results]


def get_pending_reviews() -> list[dict]:
    """获取所有待审核项"""
    items = []
    for item in _review_queue:
        if item.status == "pending":
            items.append({
                "id": item.id,
                "source_text": item.source_text[:200] + "..." if len(item.source_text) > 200 else item.source_text,
                "entities": [
                    {
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "description": e.description,
                        "courtesy_name": e.courtesy_name,
                        "origin": e.origin,
                        "year": e.year,
                        "leader": e.leader,
                    }
                    for e in item.entities
                ],
                "relations": [
                    {
                        "source_name": r.source_name,
                        "source_type": r.source_type,
                        "target_name": r.target_name,
                        "target_type": r.target_type,
                        "relation_type": r.relation_type,
                        "description": r.description,
                    }
                    for r in item.relations
                ],
                "status": item.status,
            })
    return items


def get_review_detail(review_id: int) -> dict | None:
    """获取审核项详情"""
    for item in _review_queue:
        if item.id == review_id:
            return {
                "id": item.id,
                "source_text": item.source_text,
                "entities": [
                    {
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "description": e.description,
                        "courtesy_name": e.courtesy_name,
                        "origin": e.origin,
                        "birth_year": e.birth_year,
                        "death_year": e.death_year,
                        "year": e.year,
                        "location": e.location,
                        "leader": e.leader,
                        "period": e.period,
                    }
                    for e in item.entities
                ],
                "relations": [
                    {
                        "source_name": r.source_name,
                        "source_type": r.source_type,
                        "target_name": r.target_name,
                        "target_type": r.target_type,
                        "relation_type": r.relation_type,
                        "description": r.description,
                    }
                    for r in item.relations
                ],
                "status": item.status,
            }
    return None


def approve_review(review_id: int,
                   edited_entities: list[dict] | None = None,
                   edited_relations: list[dict] | None = None) -> dict:
    """审核通过，写入 SQLite

    Args:
        review_id: 审核项 ID
        edited_entities: 修正后的实体列表（可选，不传则用原始抽取结果）
        edited_relations: 修正后的关系列表（可选）

    Returns:
        写入结果统计
    """
    init_db()

    item = None
    for r in _review_queue:
        if r.id == review_id:
            item = r
            break

    if not item:
        return {"success": False, "message": f"审核项 {review_id} 不存在"}

    if item.status != "pending":
        return {"success": False, "message": f"审核项 {review_id} 已处理（{item.status}）"}

    # 使用修正后的数据或原始数据
    entities_data = edited_entities or [
        {
            "name": e.name,
            "entity_type": e.entity_type,
            "description": e.description,
            "courtesy_name": e.courtesy_name,
            "origin": e.origin,
            "birth_year": e.birth_year,
            "death_year": e.death_year,
            "year": e.year,
            "location": e.location,
            "leader": e.leader,
            "period": e.period,
        }
        for e in item.entities
    ]

    relations_data = edited_relations or [
        {
            "source_name": r.source_name,
            "source_type": r.source_type,
            "target_name": r.target_name,
            "target_type": r.target_type,
            "relation_type": r.relation_type,
            "description": r.description,
        }
        for r in item.relations
    ]

    # 写入实体
    entity_id_map: dict[str, int] = {}  # "type:name" -> db_id
    entities_written = 0

    for ent in entities_data:
        name = ent.get("name", "").strip()
        etype = ent.get("entity_type", "").strip()
        if not name or not etype:
            continue

        try:
            if etype == "person":
                db_id = create_person(
                    name=name,
                    courtesy_name=ent.get("courtesy_name", ""),
                    origin=ent.get("origin", ""),
                    birth_year=ent.get("birth_year", ""),
                    death_year=ent.get("death_year", ""),
                    description=ent.get("description", ""),
                    source=item.source_text[:100],
                )
            elif etype == "event":
                db_id = create_event(
                    name=name,
                    year=ent.get("year", ""),
                    location=ent.get("location", ""),
                    description=ent.get("description", ""),
                    source=item.source_text[:100],
                )
            elif etype == "force":
                db_id = create_force(
                    name=name,
                    leader=ent.get("leader", ""),
                    period=ent.get("period", ""),
                    description=ent.get("description", ""),
                    source=item.source_text[:100],
                )
            else:
                continue

            entity_id_map[f"{etype}:{name}"] = db_id
            entities_written += 1
        except Exception as e:
            print(f"警告：写入实体 {name} 失败: {e}")

    # 写入关系
    relations_written = 0

    for rel in relations_data:
        src_key = f"{rel.get('source_type', '')}:{rel.get('source_name', '')}"
        tgt_key = f"{rel.get('target_type', '')}:{rel.get('target_name', '')}"

        src_id = entity_id_map.get(src_key)
        tgt_id = entity_id_map.get(tgt_key)

        if not src_id or not tgt_id:
            # 关系两端的实体不存在，跳过
            continue

        try:
            create_relation(
                source_type=rel["source_type"],
                source_id=src_id,
                target_type=rel["target_type"],
                target_id=tgt_id,
                relation_type=rel["relation_type"],
                description=rel.get("description", ""),
                source=item.source_text[:100],
            )
            relations_written += 1
        except Exception as e:
            print(f"警告：写入关系失败: {e}")

    item.status = "approved"

    return {
        "success": True,
        "message": f"审核通过，已写入 {entities_written} 个实体和 {relations_written} 个关系",
        "entities_written": entities_written,
        "relations_written": relations_written,
    }


def reject_review(review_id: int, reason: str = "") -> dict:
    """拒绝审核项"""
    for item in _review_queue:
        if item.id == review_id:
            if item.status != "pending":
                return {"success": False, "message": f"审核项 {review_id} 已处理（{item.status}）"}
            item.status = "rejected"
            return {"success": True, "message": f"已拒绝审核项 {review_id}"}

    return {"success": False, "message": f"审核项 {review_id} 不存在"}


def get_review_stats() -> dict:
    """获取审核统计"""
    total = len(_review_queue)
    pending = sum(1 for r in _review_queue if r.status == "pending")
    approved = sum(1 for r in _review_queue if r.status == "approved")
    rejected = sum(1 for r in _review_queue if r.status == "rejected")

    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
    }
