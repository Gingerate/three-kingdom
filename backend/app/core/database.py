"""SQLite 数据库管理 —— 知识图谱实体与关系存储"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

from app.core.config import settings


def get_db_path() -> Path:
    return Path(settings.sqlite_db_path)


def init_db():
    """初始化数据库，创建表结构"""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 初始化去重表
    from app.kg.dedup import init_dedup_table
    init_dedup_table()

    with get_connection() as conn:
        # WAL 模式是数据库级设置，只需设置一次
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            -- 实体表：人物
            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                courtesy_name TEXT,          -- 字
                origin TEXT,                 -- 籍贯
                birth_year TEXT,
                death_year TEXT,
                description TEXT DEFAULT '',
                source TEXT DEFAULT '',      -- 来源（三国志/演义/论文）
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 实体表：事件
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                year TEXT,                   -- 发生年份（如"建安五年"或"200"）
                location TEXT,
                description TEXT DEFAULT '',
                source TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 实体表：势力
            CREATE TABLE IF NOT EXISTS forces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                leader TEXT,                 -- 领袖
                period TEXT,                 -- 存续时期
                description TEXT DEFAULT '',
                source TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 关系表
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,   -- person/event/force
                source_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,   -- person/event/force
                target_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL, -- belongs_to/participated/ally/rival/holds_office 等
                description TEXT DEFAULT '',
                source TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_type, source_id, target_type, target_id, relation_type)
            );

            -- 对话记录表
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,           -- 'user' / 'assistant'
                content TEXT NOT NULL,
                sources TEXT DEFAULT '[]',    -- JSON array of sources (仅 assistant)
                route TEXT DEFAULT '',        -- simple/complex (仅 assistant)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
            CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at);

            -- 知识摘要表（从对话中提炼的知识）
            CREATE TABLE IF NOT EXISTS knowledge_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                summary TEXT NOT NULL,        -- 3-5句精华摘要
                sources TEXT DEFAULT '[]',    -- 原始来源
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_ks_session ON knowledge_summaries(session_id);

            -- Wiki 页面表
            CREATE TABLE IF NOT EXISTS wiki_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,        -- markdown 内容
                topic TEXT DEFAULT '',        -- 主题标签
                source_sessions TEXT DEFAULT '[]',  -- 来源 session_ids
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_wiki_topic ON wiki_pages(topic);

            -- 审核队列表
            CREATE TABLE IF NOT EXISTS review_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_text TEXT NOT NULL,
                entities TEXT NOT NULL DEFAULT '[]',     -- JSON array of extracted entities
                relations TEXT NOT NULL DEFAULT '[]',    -- JSON array of extracted relations
                status TEXT NOT NULL DEFAULT 'pending',   -- pending / approved / rejected
                reason TEXT DEFAULT '',                   -- 拒绝理由
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_review_status ON review_items(status);

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
            CREATE INDEX IF NOT EXISTS idx_events_name ON events(name);
            CREATE INDEX IF NOT EXISTS idx_forces_name ON forces(name);
            CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_type, source_id);
            CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_type, target_id);
        """)


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(str(get_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==================== 对话记录 ====================


def save_message(session_id: str, role: str, content: str,
                 sources: list[str] | None = None, route: str = ""):
    """保存一条对话消息"""
    import json
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, role, content, sources, route) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, json.dumps(sources or []), route),
        )


def get_conversation_history(session_id: str, limit: int = 20) -> list[dict]:
    """获取指定会话的对话历史"""
    import json
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content, sources, route, created_at FROM conversations "
            "WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    result = []
    for r in rows:
        try:
            sources = json.loads(r["sources"])
        except (json.JSONDecodeError, TypeError):
            sources = []
        result.append({
            "role": r["role"],
            "content": r["content"],
            "sources": sources,
            "route": r["route"],
            "created_at": r["created_at"],
        })
    return result


def get_recent_sessions(limit: int = 50) -> list[dict]:
    """获取最近的会话列表"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT session_id, MIN(created_at) as started, MAX(created_at) as last_active, "
            "COUNT(*) as message_count FROM conversations "
            "GROUP BY session_id ORDER BY last_active DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== 知识摘要 ====================


def save_knowledge_summary(session_id: str, question: str, summary: str,
                           sources: list[str] | None = None):
    """保存一条知识摘要"""
    import json
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO knowledge_summaries (session_id, question, summary, sources) VALUES (?, ?, ?, ?)",
            (session_id, question, summary, json.dumps(sources or [])),
        )


def get_knowledge_summaries(session_id: str | None = None, limit: int = 100) -> list[dict]:
    """获取知识摘要"""
    import json
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM knowledge_summaries WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_summaries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    result = []
    for r in rows:
        try:
            sources = json.loads(r["sources"])
        except (json.JSONDecodeError, TypeError):
            sources = []
        result.append({
            "id": r["id"],
            "session_id": r["session_id"],
            "question": r["question"],
            "summary": r["summary"],
            "sources": sources,
            "created_at": r["created_at"],
        })
    return result


def cleanup_old_knowledge_summaries(days: int = 30) -> int:
    """清理指定天数之前的知识摘要

    Args:
        days: 保留最近 N 天的数据

    Returns:
        删除的记录数
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM knowledge_summaries WHERE created_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        return cursor.rowcount


def get_knowledge_summaries_stats() -> dict:
    """获取知识摘要统计信息"""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_summaries").fetchone()["cnt"]
        oldest = conn.execute("SELECT MIN(created_at) as oldest FROM knowledge_summaries").fetchone()["oldest"]
        newest = conn.execute("SELECT MAX(created_at) as newest FROM knowledge_summaries").fetchone()["newest"]
    return {
        "total": total,
        "oldest": oldest,
        "newest": newest,
    }


# ==================== Wiki 页面 ====================


def save_wiki_page(title: str, content: str, topic: str = "",
                   source_sessions: list[str] | None = None) -> int:
    """保存一篇 Wiki 页面（按 title 去重，存在则更新）"""
    import json
    sessions_json = json.dumps(source_sessions or [])
    with get_connection() as conn:
        # 检查是否已存在同标题页面
        existing = conn.execute(
            "SELECT id FROM wiki_pages WHERE title = ?", (title,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE wiki_pages SET content = ?, topic = ?, source_sessions = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (content, topic, sessions_json, existing["id"]),
            )
            return existing["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO wiki_pages (title, content, topic, source_sessions) VALUES (?, ?, ?, ?)",
                (title, content, topic, sessions_json),
            )
            return cursor.lastrowid


def update_wiki_page(page_id: int, title: str | None = None,
                     content: str | None = None, topic: str | None = None) -> bool:
    """更新 Wiki 页面"""
    with get_connection() as conn:
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if topic is not None:
            updates.append("topic = ?")
            params.append(topic)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(page_id)
        conn.execute(
            f"UPDATE wiki_pages SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        return True


def delete_wiki_page(page_id: int) -> bool:
    """删除 Wiki 页面"""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM wiki_pages WHERE id = ?", (page_id,))
        return cursor.rowcount > 0


def get_wiki_pages(topic: str | None = None, limit: int = 50,
                   include_content: bool = False) -> list[dict]:
    """获取 Wiki 页面列表

    Args:
        topic: 按主题过滤
        limit: 返回数量限制
        include_content: 是否包含完整内容（列表接口默认不包含）
    """
    import json
    with get_connection() as conn:
        if topic:
            rows = conn.execute(
                "SELECT * FROM wiki_pages WHERE topic = ? ORDER BY updated_at DESC LIMIT ?",
                (topic, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM wiki_pages ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    result = []
    for r in rows:
        try:
            source_sessions = json.loads(r["source_sessions"])
        except (json.JSONDecodeError, TypeError):
            source_sessions = []
        item = {
            "id": r["id"],
            "title": r["title"],
            "topic": r["topic"],
            "source_sessions": source_sessions,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        if include_content:
            item["content"] = r["content"]
        else:
            # 只返回前 150 个字符用于预览
            item["content_preview"] = r["content"][:150] + "..." if len(r["content"]) > 150 else r["content"]
        result.append(item)
    return result


def get_wiki_page(page_id: int) -> dict | None:
    """获取单篇 Wiki 页面"""
    import json
    with get_connection() as conn:
        r = conn.execute(
            "SELECT * FROM wiki_pages WHERE id = ?", (page_id,)
        ).fetchone()
    if not r:
        return None
    try:
        source_sessions = json.loads(r["source_sessions"])
    except (json.JSONDecodeError, TypeError):
        source_sessions = []
    return {
        "id": r["id"],
        "title": r["title"],
        "content": r["content"],
        "topic": r["topic"],
        "source_sessions": source_sessions,
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


# ==================== 审核队列 ====================


def save_review_item(source_text: str, entities: list[dict], relations: list[dict]) -> int:
    """保存一条审核记录，返回 ID"""
    import json
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO review_items (source_text, entities, relations) VALUES (?, ?, ?)",
            (source_text, json.dumps(entities, ensure_ascii=False), json.dumps(relations, ensure_ascii=False)),
        )
        return cursor.lastrowid


def get_review_items_by_status(status: str) -> list[dict]:
    """按状态获取审核记录"""
    import json
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM review_items WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    result = []
    for r in rows:
        try:
            entities = json.loads(r["entities"])
        except (json.JSONDecodeError, TypeError):
            entities = []
        try:
            relations = json.loads(r["relations"])
        except (json.JSONDecodeError, TypeError):
            relations = []
        result.append({
            "id": r["id"],
            "source_text": r["source_text"],
            "entities": entities,
            "relations": relations,
            "status": r["status"],
            "reason": r["reason"],
            "created_at": r["created_at"],
        })
    return result


def get_review_item(review_id: int) -> dict | None:
    """获取单条审核记录"""
    import json
    with get_connection() as conn:
        r = conn.execute(
            "SELECT * FROM review_items WHERE id = ?", (review_id,)
        ).fetchone()
    if not r:
        return None
    try:
        entities = json.loads(r["entities"])
    except (json.JSONDecodeError, TypeError):
        entities = []
    try:
        relations = json.loads(r["relations"])
    except (json.JSONDecodeError, TypeError):
        relations = []
    return {
        "id": r["id"],
        "source_text": r["source_text"],
        "entities": entities,
        "relations": relations,
        "status": r["status"],
        "reason": r["reason"],
        "created_at": r["created_at"],
    }


def update_review_status(review_id: int, status: str, reason: str = ""):
    """更新审核记录状态"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE review_items SET status = ?, reason = ? WHERE id = ?",
            (status, reason, review_id),
        )


def get_review_stats_from_db() -> dict:
    """获取审核统计"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM review_items GROUP BY status"
        ).fetchall()
    stats = {r["status"]: r["cnt"] for r in rows}
    return {
        "total": sum(stats.values()),
        "pending": stats.get("pending", 0),
        "approved": stats.get("approved", 0),
        "rejected": stats.get("rejected", 0),
    }
