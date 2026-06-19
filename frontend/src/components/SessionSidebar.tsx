import { useEffect, useState } from 'react';
import { Button, Popconfirm, message } from 'antd';
import { HistoryOutlined, CloseOutlined, MessageOutlined, DeleteOutlined } from '@ant-design/icons';
import { useChat } from '../contexts/ChatContext';
import { deleteSession, getSessionStats, type SessionInfo } from '../services/api';

interface SessionSidebarProps {
  visible: boolean;
  onClose: () => void;
}

/** 对话历史侧栏 */
export default function SessionSidebar({ visible, onClose }: SessionSidebarProps) {
  const { sessions, loadSessions, switchSession, sessionId } = useChat();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [stats, setStats] = useState<{
    total_sessions: number;
    total_messages: number;
    avg_answer_length: number;
    recent_active_sessions: number;
  } | null>(null);

  useEffect(() => {
    if (visible) {
      loadSessions();
      getSessionStats().then(setStats).catch(() => {});
    }
  }, [visible, loadSessions]);

  const handleSwitch = (sid: string) => {
    if (sid === sessionId) return;
    switchSession(sid);
    onClose();
  };

  const handleDelete = async (sid: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setDeletingId(sid);
    try {
      await deleteSession(sid);
      message.success('已删除');
      loadSessions();
    } catch {
      message.error('删除失败');
    } finally {
      setDeletingId(null);
    }
  };

  // 按日期分组
  const grouped = groupByDate(sessions);

  return (
    <>
      {/* 遮罩 */}
      {visible && (
        <div
          className="session-overlay"
          onClick={onClose}
        />
      )}

      {/* 侧栏 */}
      <div className={`session-sidebar ${visible ? 'open' : ''}`}>
        <div className="session-sidebar-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <HistoryOutlined />
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14 }}>
              对话历史
            </span>
          </span>
          <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} />
        </div>

        {/* 统计信息 */}
        {stats && (
          <div className="session-stats">
            <div className="session-stat">
              <span className="session-stat-value">{stats.total_sessions}</span>
              <span className="session-stat-label">总会话</span>
            </div>
            <div className="session-stat">
              <span className="session-stat-value">{stats.total_messages}</span>
              <span className="session-stat-label">总消息</span>
            </div>
            <div className="session-stat">
              <span className="session-stat-value">{stats.recent_active_sessions}</span>
              <span className="session-stat-label">近7天</span>
            </div>
          </div>
        )}

        <div className="session-sidebar-body">
          {sessions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-ink-4)', fontSize: 13 }}>
              暂无历史对话
            </div>
          ) : (
            grouped.map(([date, items]) => (
              <div key={date} className="session-group">
                <div className="session-date">{date}</div>
                {items.map((s) => (
                  <div
                    key={s.session_id}
                    className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
                    onClick={() => handleSwitch(s.session_id)}
                    role="button"
                    tabIndex={0}
                  >
                    <MessageOutlined style={{ fontSize: 13, flexShrink: 0, marginTop: 2 }} />
                    <div className="session-item-content">
                      <div className="session-item-question">{s.first_question}</div>
                      <div className="session-item-meta">{s.message_count} 轮对话</div>
                    </div>
                    <Popconfirm
                      title="确定删除此对话？"
                      description="删除后不可恢复"
                      onConfirm={(e) => handleDelete(s.session_id, e)}
                      onCancel={(e) => e?.stopPropagation()}
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                    >
                      <button
                        className="session-delete-btn"
                        onClick={(e) => e.stopPropagation()}
                        disabled={deletingId === s.session_id}
                        title="删除对话"
                      >
                        <DeleteOutlined />
                      </button>
                    </Popconfirm>
                  </div>
                ))}
              </div>
            ))
          )}
        </div>

        <style>{`
          .session-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.2);
            z-index: 900;
            animation: fade-in 0.2s ease;
          }

          @keyframes fade-in {
            from { opacity: 0; }
          }

          .session-sidebar {
            position: fixed;
            right: -320px;
            top: 0;
            bottom: 0;
            width: 320px;
            background: var(--color-paper-2);
            border-left: 1px solid var(--color-rule);
            z-index: 950;
            display: flex;
            flex-direction: column;
            transition: right 0.3s var(--ease-out);
            box-shadow: -4px 0 24px rgba(0, 0, 0, 0.06);
          }

          .session-sidebar.open {
            right: 0;
          }

          .session-sidebar-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            border-bottom: 1px solid var(--color-rule);
            flex-shrink: 0;
          }

          .session-stats {
            display: flex;
            justify-content: space-around;
            padding: 10px 16px;
            border-bottom: 1px solid var(--color-rule-2);
            background: var(--color-paper-3);
          }

          .session-stat {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
          }

          .session-stat-value {
            font-family: var(--font-display);
            font-size: 16px;
            font-weight: 700;
            color: var(--color-ink);
          }

          .session-stat-label {
            font-size: 11px;
            color: var(--color-ink-4);
          }

          .session-sidebar-body {
            flex: 1;
            overflow-y: auto;
            padding: 8px 0;
          }

          .session-group {
            margin-bottom: 4px;
          }

          .session-date {
            font-family: var(--font-display);
            font-size: 11px;
            font-weight: 700;
            color: var(--color-ink-4);
            padding: 8px 16px 4px;
            letter-spacing: 1px;
          }

          .session-item {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            width: 100%;
            padding: 10px 16px;
            background: none;
            border: none;
            cursor: pointer;
            text-align: left;
            transition: background var(--dur-fast) var(--ease-out);
            color: var(--color-ink-3);
          }

          .session-item:hover {
            background: var(--color-paper-hover);
          }

          .session-item.active {
            background: var(--color-accent-bg);
            color: var(--color-accent);
          }

          .session-item-content {
            flex: 1;
            min-width: 0;
          }

          .session-item-question {
            font-size: 13px;
            color: var(--color-ink-2);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 1.5;
          }

          .session-item.active .session-item-question {
            color: var(--color-accent);
          }

          .session-item-meta {
            font-size: 11px;
            color: var(--color-ink-4);
            margin-top: 2px;
          }

          .session-delete-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border: none;
            background: none;
            cursor: pointer;
            color: var(--color-ink-4);
            border-radius: var(--radius-xs);
            transition: all var(--dur-fast) var(--ease-out);
            font-size: 12px;
            flex-shrink: 0;
            opacity: 0;
          }

          .session-item:hover .session-delete-btn {
            opacity: 1;
          }

          .session-delete-btn:hover {
            color: var(--color-accent);
            background: var(--color-accent-bg);
          }

          .session-delete-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }
        `}</style>
      </div>
    </>
  );
}

/** 按日期分组会话 */
function groupByDate(sessions: SessionInfo[]): [string, SessionInfo[]][] {
  const groups = new Map<string, SessionInfo[]>();
  const now = new Date();
  const today = now.toDateString();
  const yesterday = new Date(now.getTime() - 86400000).toDateString();

  for (const s of sessions) {
    const d = new Date(s.last_active);
    const ds = d.toDateString();
    let label: string;
    if (ds === today) label = '今天';
    else if (ds === yesterday) label = '昨天';
    else label = d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });

    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(s);
  }

  return Array.from(groups.entries());
}
