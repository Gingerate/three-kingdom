"""入库去重管理 —— chunk 级哈希去重，避免重复入库"""

import hashlib
from datetime import datetime
from contextlib import contextmanager

from app.core.database import get_connection, init_db


def init_dedup_table():
    """初始化去重记录表"""
    with get_connection() as conn:
        conn.executescript("""
            -- 入库记录表：记录已入库的 chunk 哈希
            CREATE TABLE IF NOT EXISTS ingestion_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_hash TEXT NOT NULL UNIQUE,      -- SHA256 哈希
                source_file TEXT NOT NULL,             -- 源文件路径（相对于 raw/）
                source_name TEXT DEFAULT '',           -- 语义标识（如 "三国志"）
                chunk_index INTEGER NOT NULL,          -- chunk 在文件中的索引
                chunk_content TEXT NOT NULL,           -- chunk 内容（用于预览）
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_chunk_hash ON ingestion_records(chunk_hash);
            CREATE INDEX IF NOT EXISTS idx_source_file ON ingestion_records(source_file);
        """)

        # 迁移：添加 source_name 字段（如果不存在）
        try:
            conn.execute("SELECT source_name FROM ingestion_records LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE ingestion_records ADD COLUMN source_name TEXT DEFAULT ''")
            print("[迁移] 已添加 source_name 字段")


def calculate_chunk_hash(content: str) -> str:
    """计算 chunk 内容的 SHA256 哈希"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def is_chunk_exists(chunk_hash: str) -> bool:
    """检查 chunk 是否已存在"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM ingestion_records WHERE chunk_hash = ?",
            (chunk_hash,)
        ).fetchone()
        return row is not None


def get_existing_hashes(source_file: str) -> set[str]:
    """获取指定文件已存在的 chunk 哈希集合"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT chunk_hash FROM ingestion_records WHERE source_file = ?",
            (source_file,)
        ).fetchall()
        return {row['chunk_hash'] for row in rows}


def get_all_existing_hashes() -> set[str]:
    """获取所有已存在的 chunk 哈希集合"""
    with get_connection() as conn:
        rows = conn.execute("SELECT chunk_hash FROM ingestion_records").fetchall()
        return {row['chunk_hash'] for row in rows}


def add_record(chunk_hash: str, source_file: str, chunk_index: int, chunk_content: str,
               source_name: str = ""):
    """添加一条入库记录"""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ingestion_records (chunk_hash, source_file, source_name, chunk_index, chunk_content) "
            "VALUES (?, ?, ?, ?, ?)",
            (chunk_hash, source_file, source_name, chunk_index, chunk_content)
        )


def add_records_batch(records: list[dict]):
    """批量添加入库记录"""
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO ingestion_records (chunk_hash, source_file, source_name, chunk_index, chunk_content) "
            "VALUES (:chunk_hash, :source_file, :source_name, :chunk_index, :chunk_content)",
            records
        )


def delete_records_by_file(source_file: str):
    """删除指定文件的所有入库记录"""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM ingestion_records WHERE source_file = ?",
            (source_file,)
        )


def delete_records_by_files(source_files: list[str]):
    """批量删除多个文件的入库记录"""
    if not source_files:
        return
    placeholders = ','.join(['?' for _ in source_files])
    with get_connection() as conn:
        conn.execute(
            f"DELETE FROM ingestion_records WHERE source_file IN ({placeholders})",
            source_files
        )


def get_all_files() -> list[dict]:
    """获取所有已入库文件的列表和 chunk 数量"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_file, source_name, COUNT(*) as chunk_count, "
            "MIN(created_at) as first_ingested, MAX(created_at) as last_ingested "
            "FROM ingestion_records GROUP BY source_file ORDER BY last_ingested DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_file_chunks(source_file: str) -> list[dict]:
    """获取指定文件的所有 chunk 记录"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM ingestion_records WHERE source_file = ? ORDER BY chunk_index",
            (source_file,)
        ).fetchall()
        return [dict(row) for row in rows]


def cleanup_duplicates() -> int:
    """清理重复的 chunk 记录，保留第一条，返回清理数量"""
    with get_connection() as conn:
        # 找出重复的 chunk_hash
        duplicates = conn.execute(
            "SELECT chunk_hash, COUNT(*) as cnt FROM ingestion_records "
            "GROUP BY chunk_hash HAVING cnt > 1"
        ).fetchall()

        cleaned_count = 0
        for row in duplicates:
            chunk_hash = row['chunk_hash']
            # 保留第一条，删除其他
            records = conn.execute(
                "SELECT id FROM ingestion_records WHERE chunk_hash = ? ORDER BY id",
                (chunk_hash,)
            ).fetchall()
            # 删除除第一条外的所有记录
            ids_to_delete = [r['id'] for r in records[1:]]
            if ids_to_delete:
                placeholders = ','.join(['?' for _ in ids_to_delete])
                conn.execute(
                    f"DELETE FROM ingestion_records WHERE id IN ({placeholders})",
                    ids_to_delete
                )
                cleaned_count += len(ids_to_delete)

        return cleaned_count


def cleanup_all():
    """清空所有入库记录"""
    with get_connection() as conn:
        conn.execute("DELETE FROM ingestion_records")


def get_ingestion_stats() -> dict:
    """获取入库统计信息"""
    with get_connection() as conn:
        total_chunks = conn.execute("SELECT COUNT(*) as cnt FROM ingestion_records").fetchone()['cnt']
        total_files = conn.execute("SELECT COUNT(DISTINCT source_file) as cnt FROM ingestion_records").fetchone()['cnt']
        return {
            "total_chunks": total_chunks,
            "total_files": total_files
        }
