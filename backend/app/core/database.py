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
    conn = sqlite3.connect(str(get_db_path()))
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
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "sources": json.loads(r["sources"]),
            "route": r["route"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


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
    return [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "question": r["question"],
            "summary": r["summary"],
            "sources": json.loads(r["sources"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ==================== Wiki 页面 ====================


def save_wiki_page(title: str, content: str, topic: str = "",
                   source_sessions: list[str] | None = None):
    """保存一篇 Wiki 页面"""
    import json
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO wiki_pages (title, content, topic, source_sessions) VALUES (?, ?, ?, ?)",
            (title, content, topic, json.dumps(source_sessions or [])),
        )


def get_wiki_pages(topic: str | None = None, limit: int = 50) -> list[dict]:
    """获取 Wiki 页面列表"""
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
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "content": r["content"],
            "topic": r["topic"],
            "source_sessions": json.loads(r["source_sessions"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_wiki_page(page_id: int) -> dict | None:
    """获取单篇 Wiki 页面"""
    import json
    with get_connection() as conn:
        r = conn.execute(
            "SELECT * FROM wiki_pages WHERE id = ?", (page_id,)
        ).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "title": r["title"],
        "content": r["content"],
        "topic": r["topic"],
        "source_sessions": json.loads(r["source_sessions"]),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
