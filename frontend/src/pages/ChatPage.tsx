import { useState, useRef, useEffect } from 'react';
import { Input, Button, Tag, Spin, Divider } from 'antd';
import { SendOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons';
import { useChat } from '../contexts/ChatContext';

const QUICK_QUESTIONS = [
  '官渡之战的经过是什么？',
  '诸葛亮的北伐策略有哪些？',
  '赤壁之战对天下格局的影响？',
  '三国各自的用人之道有何不同？',
];

export default function ChatPage() {
  const { messages, loading, streamStatus, handleSend, clearMessages } = useChat();
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // 智能滚动：只在用户已经在底部附近时自动滚动
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
    if (isNearBottom) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const onSend = async (text?: string) => {
    const question = (text || input).trim();
    if (!question || loading) return;
    setInput('');
    await handleSend(question);
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
        {messages.length > 0 && (
          <Button
            icon={<PlusOutlined />}
            onClick={clearMessages}
            size="small"
          >
            新对话
          </Button>
        )}
      </div>

      {/* 消息区 */}
      <div ref={scrollContainerRef} style={{ flex: 1, overflow: 'auto', padding: '24px 32px' }}>
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
                  onClick={() => onSend(q)}
                  aria-label={`快速提问：${q}`}
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
            onPressEnter={() => onSend()}
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
            onClick={() => onSend()}
            loading={loading}
            style={{ borderRadius: 'var(--r-sm)' }}
          />
        </div>
      </div>
    </div>
  );
}
