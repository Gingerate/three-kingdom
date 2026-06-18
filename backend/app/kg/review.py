"""抽取结果审核模块 —— 人工审核/修正后写入 SQLite（持久化存储）"""

from __future__ import annotations

from app.kg.extractor import ExtractionResult, ExtractedEntity, ExtractedRelation
from app.models.crud import (
    create_person, create_event, create_force, create_relation,
)
from app.core.database import (
    init_db,
    save_review_item,
    get_review_items_by_status,
    get_review_item,
    update_review_status,
    get_review_stats_from_db,
)


def _entities_to_dicts(entities: list[ExtractedEntity]) -> list[dict]:
    """将 ExtractedEntity 列表转为 dict 列表"""
    return [
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
        for e in entities
    ]


def _relations_to_dicts(relations: list[ExtractedRelation]) -> list[dict]:
    """将 ExtractedRelation 列表转为 dict 列表"""
    return [
        {
            "source_name": r.source_name,
            "source_type": r.source_type,
            "target_name": r.target_name,
            "target_type": r.target_type,
            "relation_type": r.relation_type,
            "description": r.description,
        }
        for r in relations
    ]


def add_to_review_queue(result: ExtractionResult) -> int:
    """将抽取结果加入待审核队列

    Returns:
        审核项 ID
    """
    init_db()
    entities = _entities_to_dicts(result.entities)
    relations = _relations_to_dicts(result.relations)
    return save_review_item(result.source_text, entities, relations)


def add_batch_to_review_queue(results: list[ExtractionResult]) -> list[int]:
    """批量加入审核队列"""
    return [add_to_review_queue(r) for r in results]


def get_pending_reviews() -> list[dict]:
    """获取所有待审核项（摘要版，不返回完整 source_text）"""
    items = get_review_items_by_status("pending")
    for item in items:
        item["source_text"] = item["source_text"][:200] + "..." if len(item["source_text"]) > 200 else item["source_text"]
    return items


def get_review_detail(review_id: int) -> dict | None:
    """获取审核项详情"""
    return get_review_item(review_id)


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

    item = get_review_item(review_id)
    if not item:
        return {"success": False, "message": f"审核项 {review_id} 不存在"}

    if item["status"] != "pending":
        return {"success": False, "message": f"审核项 {review_id} 已处理（{item['status']}）"}

    # 使用修正后的数据或原始数据
    entities_data = edited_entities or item["entities"]
    relations_data = edited_relations or item["relations"]

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
                    source=item["source_text"][:100],
                )
            elif etype == "event":
                db_id = create_event(
                    name=name,
                    year=ent.get("year", ""),
                    location=ent.get("location", ""),
                    description=ent.get("description", ""),
                    source=item["source_text"][:100],
                )
            elif etype == "force":
                db_id = create_force(
                    name=name,
                    leader=ent.get("leader", ""),
                    period=ent.get("period", ""),
                    description=ent.get("description", ""),
                    source=item["source_text"][:100],
                )
            else:
                continue

            entity_id_map[f"{etype}:{name}"] = db_id
            entities_written += 1
        except Exception as e:
            print(f"警告：写入实体 {name} 失败: {e}")

    # 写入关系
    relations_written = 0

    # 预加载数据库中已有的实体，用于补全跨批次引用
    def _lookup_entity_id(etype: str, ename: str) -> int | None:
        """先查当前批次的 entity_id_map，再查数据库"""
        key = f"{etype}:{ename}"
        if key in entity_id_map:
            return entity_id_map[key]
        # 回退到数据库查询
        try:
            from app.models.crud import get_person, get_event, get_force
            lookup = {"person": get_person, "event": get_event, "force": get_force}
            entity = lookup.get(etype, lambda _: None)(ename)
            if entity:
                entity_id_map[key] = entity["id"]  # 缓存
                return entity["id"]
        except Exception:
            pass
        return None

    for rel in relations_data:
        src_type = rel.get('source_type', '')
        src_name = rel.get('source_name', '')
        tgt_type = rel.get('target_type', '')
        tgt_name = rel.get('target_name', '')

        src_id = _lookup_entity_id(src_type, src_name)
        tgt_id = _lookup_entity_id(tgt_type, tgt_name)

        if not src_id or not tgt_id:
            print(f"警告：跳过关系 {src_name}→{tgt_name}，实体不存在")
            continue

        try:
            create_relation(
                source_type=rel["source_type"],
                source_id=src_id,
                target_type=rel["target_type"],
                target_id=tgt_id,
                relation_type=rel["relation_type"],
                description=rel.get("description", ""),
                source=item["source_text"][:100],
            )
            relations_written += 1
        except Exception as e:
            print(f"警告：写入关系失败: {e}")

    # 更新审核状态
    update_review_status(review_id, "approved")

    return {
        "success": True,
        "message": f"审核通过，已写入 {entities_written} 个实体和 {relations_written} 个关系",
        "entities_written": entities_written,
        "relations_written": relations_written,
    }


def reject_review(review_id: int, reason: str = "") -> dict:
    """拒绝审核项"""
    item = get_review_item(review_id)
    if not item:
        return {"success": False, "message": f"审核项 {review_id} 不存在"}

    if item["status"] != "pending":
        return {"success": False, "message": f"审核项 {review_id} 已处理（{item['status']}）"}

    update_review_status(review_id, "rejected", reason)
    return {"success": True, "message": f"已拒绝审核项 {review_id}"}


def get_review_stats() -> dict:
    """获取审核统计"""
    return get_review_stats_from_db()
