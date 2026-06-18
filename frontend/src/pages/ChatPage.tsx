import { useState, useRef, useEffect } from 'react';
import { Input, Button, Tag, Spin, Divider } from 'antd';
import { SendOutlined, LinkOutlined } from '@ant-design/icons';
import { chatStream, type StreamEvent } from '../services/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  route?: string;
  subQuestions?: string[];
  isStreaming?: boolean;
}

const QUICK_QUESTIONS = [
  '官渡之战的经过是什么？',
  '诸葛亮的北伐策略有哪些？',
  '赤壁之战对天下格局的影响？',
  '三国各自的用人之道有何不同？',
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (text?: string) => {
    const question = (text || input).trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setInput('');
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

    await chatStream(
      question,
      undefined,
      (event: StreamEvent) => {
        const { node, updates } = event;
        const statusMap: Record<string, string> = {
          router: '分析问题中...',
          decompose: '分解问题中...',
          retrieve: '检索资料中...',
          grade: '筛选资料中...',
          generate: '生成回答中...',
          reflect: '检查质量中...',
          finalize: '整理完成',
          increment_retry: '重新检索中...',
        };
        setStreamStatus(statusMap[node] || '');

        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            const msg = { ...updated[last] };
            if (updates.final_answer) {
              msg.content = updates.final_answer;
              msg.isStreaming = false;
            } else if (updates.generation && !msg.content) {
              msg.content = updates.generation;
            }
            if (updates.sources) msg.sources = updates.sources;
            if (updates.route) msg.route = updates.route;
            if (updates.sub_questions) msg.subQuestions = updates.sub_questions;
            updated[last] = msg;
          }
          return updated;
        });
      },
      () => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            updated[last] = { ...updated[last], isStreaming: false };
          }
          return updated;
        });
        setLoading(false);
        setStreamStatus('');
      },
      (error) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            updated[last] = {
              ...updated[last],
              content: `发生了错误：${error.message}`,
              isStreaming: false,
            };
          }
          return updated;
        });
        setLoading(false);
        setStreamStatus('');
      },
    );
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">智能问答</span>
        {messages.length > 0 && (
          <Tag style={{ fontSize: 11 }}>{messages.filter(m => m.role === 'user').length} 条对话</Tag>
        )}
        <div className="page-header-spacer" />
      </div>

      {/* 消息区 */}
      <div style={{ flex: 1, overflow: 'auto', padding: '24px 32px' }}>
        {isEmpty && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            paddingBottom: 80,
          }}>
            <div className="welcome-seal">三国</div>
            <h2 className="welcome-title">以史为鉴，可以知兴替</h2>
            <p className="welcome-sub">输入问题，从三国历史中探寻答案</p>
            <div className="quick-grid">
              {QUICK_QUESTIONS.map((q) => (
                <button
                  key={q}
                  className="quick-btn"
                  onClick={() => handleSend(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`msg ${msg.role === 'user' ? 'msg-user' : 'msg-bot'}`}>
            <div className="msg-avatar">
              {msg.role === 'user' ? '问' : '答'}
            </div>
            <div className="msg-body">
              <div style={{ whiteSpace: 'pre-wrap' }}>
                {msg.content || (msg.isStreaming ? <Spin size="small" /> : '')}
              </div>

              {msg.role === 'assistant' && msg.route && (
                <div style={{ marginTop: 8 }}>
                  <Tag
                    color={msg.route === 'complex' ? 'orange' : 'green'}
                    style={{ fontSize: 11, borderRadius: 'var(--r-xs)' }}
                  >
                    {msg.route === 'complex' ? '复杂问题' : '简单问题'}
                  </Tag>
                  {msg.subQuestions && msg.subQuestions.length > 1 && (
                    <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--ink-40)' }}>
                      子问题：{msg.subQuestions.join(' → ')}
                    </span>
                  )}
                </div>
              )}

              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <>
                  <Divider style={{ margin: '8px 0', borderColor: 'var(--border-faint)' }} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <LinkOutlined style={{ fontSize: 12, color: 'var(--ink-40)' }} />
                    {msg.sources.map((src, j) => (
                      <Tag key={j} style={{ fontSize: 11 }}>{src}</Tag>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}

        {loading && streamStatus && (
          <div style={{ textAlign: 'center', padding: '6px 0' }}>
            <span style={{ fontSize: 12, color: 'var(--ink-40)' }}>
              <Spin size="small" /> {streamStatus}
            </span>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* 输入区 */}
      <div style={{
        padding: '12px 32px 16px',
        borderTop: '1px solid var(--border)',
        background: 'var(--bg-surface)',
      }}>
        <div style={{
          display: 'flex',
          gap: 8,
          background: 'var(--bg-base)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--r-md)',
          padding: 6,
        }}>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => handleSend()}
            placeholder="输入你的三国问题..."
            disabled={loading}
            variant="borderless"
            style={{
              flex: 1,
              background: 'transparent',
              fontFamily: 'var(--font-body)',
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={() => handleSend()}
            loading={loading}
            style={{ borderRadius: 'var(--r-sm)' }}
          />
        </div>
      </div>
    </div>
  );
}
