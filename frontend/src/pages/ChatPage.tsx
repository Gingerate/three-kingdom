import { useState, useRef, useEffect } from 'react';
import { Input, Button, Tag, Divider } from 'antd';
import { SendOutlined, LinkOutlined, PlusOutlined, DownloadOutlined, HistoryOutlined, CopyOutlined, CheckOutlined, LikeOutlined, DislikeOutlined, LikeFilled, DislikeFilled } from '@ant-design/icons';
import { useChat } from '../contexts/ChatContext';
import { submitFeedback } from '../services/api';
import ChatPipelineProgress from '../components/ChatPipelineProgress';
import SessionSidebar from '../components/SessionSidebar';
import InkLoader from '../components/InkLoader';

const QUICK_QUESTIONS = [
  '官渡之战的经过是什么？',
  '诸葛亮的北伐策略有哪些？',
  '赤壁之战对天下格局的影响？',
  '三国各自的用人之道有何不同？',
];

const THREE_KINGDOMS_QUOTES = [
  { text: '鞠躬尽瘁，死而后已。', author: '诸葛亮' },
  { text: '天下大势，分久必合，合久必分。', author: '罗贯中' },
  { text: '既生瑜，何生亮。', author: '周瑜' },
  { text: '宁教我负天下人，休教天下人负我。', author: '曹操' },
  { text: '治世之能臣，乱世之奸雄。', author: '许劭' },
  { text: '勿以恶小而为之，勿以善小而不为。', author: '刘备' },
  { text: '大丈夫生于天地间，不识其主而事之，是无智也。', author: '田丰' },
  { text: '凤翱翔于千仞兮，非梧不栖。', author: '诸葛亮' },
  { text: '吾任天下之智力，以道御之，无所不可。', author: '曹操' },
  { text: '丈夫志四海，万里犹比邻。', author: '曹植' },
  { text: '对酒当歌，人生几何。', author: '曹操' },
  { text: '恢弘志士之气，不宜妄自菲薄。', author: '诸葛亮' },
  { text: '卧龙凤雏，二者得一可安天下。', author: '司马徽' },
  { text: '非淡泊无以明志，非宁静无以致远。', author: '诸葛亮' },
];

// 获取当日固定的名言（每天刷新一次）
function getDailyQuote() {
  const today = new Date();
  const dayIndex = today.getFullYear() * 366 + today.getMonth() * 31 + today.getDate();
  return THREE_KINGDOMS_QUOTES[dayIndex % THREE_KINGDOMS_QUOTES.length];
}

export default function ChatPage() {
  const { messages, loading, streamStatus, sessionId, handleSend, clearMessages } = useChat();
  const [input, setInput] = useState('');
  const [historyVisible, setHistoryVisible] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [feedbackMap, setFeedbackMap] = useState<Record<number, 'up' | 'down'>>({});
  const endRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const historyIdxRef = useRef(-1);
  const savedInputRef = useRef('');

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
    historyIdxRef.current = -1;
    savedInputRef.current = '';
    await handleSend(question);
  };

  // 用户历史问题列表
  const userQuestions = messages.filter(m => m.role === 'user').map(m => m.content);

  // 键盘导航：↑↓ 切换历史问题，Esc 清空
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (userQuestions.length === 0) return;
      if (historyIdxRef.current === -1) {
        savedInputRef.current = input;
        historyIdxRef.current = userQuestions.length - 1;
      } else if (historyIdxRef.current > 0) {
        historyIdxRef.current--;
      }
      setInput(userQuestions[historyIdxRef.current]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIdxRef.current === -1) return;
      if (historyIdxRef.current < userQuestions.length - 1) {
        historyIdxRef.current++;
        setInput(userQuestions[historyIdxRef.current]);
      } else {
        historyIdxRef.current = -1;
        setInput(savedInputRef.current);
      }
    } else if (e.key === 'Escape') {
      setInput('');
      historyIdxRef.current = -1;
      savedInputRef.current = '';
    }
  };

  // 复制消息内容
  const copyMessage = async (content: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 2000);
    } catch {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = content;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 2000);
    }
  };

  // 格式化时间
  const formatTime = (ts?: number) => {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  // 提交反馈
  const handleFeedback = async (idx: number, rating: 'up' | 'down') => {
    const msg = messages[idx];
    if (!msg || msg.role !== 'assistant') return;
    // 找到对应的问题
    const questionMsg = messages.slice(0, idx).reverse().find(m => m.role === 'user');
    if (!questionMsg) return;

    setFeedbackMap(prev => ({ ...prev, [idx]: rating }));
    try {
      await submitFeedback({
        session_id: sessionId || '',
        question: questionMsg.content,
        answer: msg.content,
        rating,
      });
    } catch {
      // 静默失败
    }
  };

  const isEmpty = messages.length === 0;
  const dailyQuote = getDailyQuote();

  // 导出对话为 Markdown
  const exportMarkdown = () => {
    const lines: string[] = ['# 三国知识库 · 对话记录', ''];
    for (const msg of messages) {
      if (msg.role === 'user') {
        lines.push(`## 🙋 提问`, '', msg.content, '');
      } else {
        lines.push(`## 📜 回答`, '');
        if (msg.route) {
          const tag = msg.route === 'complex' ? '复杂问题' : '简单问题';
          lines.push(`> 问题类型：${tag}`, '');
        }
        if (msg.subQuestions && msg.subQuestions.length > 1) {
          lines.push(`> 子问题分解：${msg.subQuestions.join(' → ')}`, '');
        }
        lines.push(msg.content, '');
        if (msg.sources && msg.sources.length > 0) {
          lines.push(`**来源：** ${msg.sources.join('、')}`, '');
        }
      }
      lines.push('---', '');
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `三国知识库-${new Date().toLocaleDateString('zh-CN')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">智能问答</span>
        {messages.length > 0 && (
          <Tag style={{ fontSize: 11 }}>{messages.filter(m => m.role === 'user').length} 条对话</Tag>
        )}
        <div className="page-header-spacer" />
        <Button
          icon={<HistoryOutlined />}
          onClick={() => setHistoryVisible(true)}
          size="small"
        >
          历史
        </Button>
        {messages.length > 0 && (
          <>
            <Button
              icon={<DownloadOutlined />}
              onClick={exportMarkdown}
              size="small"
            >
              导出
            </Button>
            <Button
              icon={<PlusOutlined />}
              onClick={clearMessages}
              size="small"
            >
              新对话
            </Button>
          </>
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
            <div className="welcome-quote">
              <p className="welcome-quote-text">「{dailyQuote.text}」</p>
              <p className="welcome-quote-author">—— {dailyQuote.author}</p>
            </div>
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
            <div className="msg-body-wrapper">
              <div className="msg-body">
                {/* 流式生成时显示管线进度 */}
                {msg.isStreaming && !msg.content && msg.currentNode && (
                  <ChatPipelineProgress
                    completedNodes={msg.completedNodes}
                    currentNode={msg.currentNode}
                  />
                )}
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {msg.content || (msg.isStreaming && !msg.currentNode ? <InkLoader size={24} /> : '')}
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
              {/* 消息元信息：时间戳 + 复制按钮 + 反馈 */}
              <div className={`msg-meta ${msg.role === 'user' ? 'msg-meta-user' : ''}`}>
                <span className="msg-time">{formatTime(msg.timestamp)}</span>
                {msg.content && !msg.isStreaming && (
                  <>
                    <button
                      className="msg-copy-btn"
                      onClick={() => copyMessage(msg.content, i)}
                      title="复制"
                    >
                      {copiedIdx === i ? <CheckOutlined /> : <CopyOutlined />}
                    </button>
                    {msg.role === 'assistant' && (
                      <>
                        <button
                          className={`msg-feedback-btn ${feedbackMap[i] === 'up' ? 'active' : ''}`}
                          onClick={() => handleFeedback(i, 'up')}
                          title="有帮助"
                        >
                          {feedbackMap[i] === 'up' ? <LikeFilled /> : <LikeOutlined />}
                        </button>
                        <button
                          className={`msg-feedback-btn ${feedbackMap[i] === 'down' ? 'active dislike' : ''}`}
                          onClick={() => handleFeedback(i, 'down')}
                          title="需要改进"
                        >
                          {feedbackMap[i] === 'down' ? <DislikeFilled /> : <DislikeOutlined />}
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        ))}

        {loading && streamStatus && (
          <div style={{ textAlign: 'center', padding: '4px 0' }}>
            <span style={{ fontSize: 11, color: 'var(--ink-40)', fontFamily: 'var(--font-display)' }}>
              {streamStatus}
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
            onPressEnter={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            onKeyDown={handleKeyDown}
            placeholder="输入你的三国问题... (Enter 发送, ↑↓ 历史)"
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

      {/* 对话历史侧栏 */}
      <SessionSidebar
        visible={historyVisible}
        onClose={() => setHistoryVisible(false)}
      />

      <style>{`
        .msg-body-wrapper {
          display: flex;
          flex-direction: column;
        }

        .msg-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 4px;
          padding: 0 4px;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .msg:hover .msg-meta {
          opacity: 1;
        }

        .msg-meta-user {
          justify-content: flex-end;
        }

        .msg-time {
          font-size: 11px;
          color: var(--ink-40);
          font-variant-numeric: tabular-nums;
        }

        .msg-copy-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          border: none;
          background: none;
          cursor: pointer;
          color: var(--ink-40);
          border-radius: var(--r-xs);
          transition: all var(--t-fast);
          font-size: 12px;
        }

        .msg-copy-btn:hover {
          color: var(--ink-100);
          background: var(--bg-hover);
        }

        .msg-feedback-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          border: none;
          background: none;
          cursor: pointer;
          color: var(--ink-40);
          border-radius: var(--r-xs);
          transition: all var(--t-fast);
          font-size: 12px;
        }

        .msg-feedback-btn:hover {
          color: var(--ink-100);
          background: var(--bg-hover);
        }

        .msg-feedback-btn.active {
          color: var(--slate-green);
        }

        .msg-feedback-btn.active.dislike {
          color: var(--vermilion);
        }

        .welcome-quote {
          text-align: center;
          margin-bottom: 16px;
          animation: fade-up 0.6s 0.25s var(--ease-out) both;
        }

        .welcome-quote-text {
          font-family: var(--font-display);
          font-size: 15px;
          color: var(--ink-60);
          line-height: 1.8;
          font-style: italic;
        }

        .welcome-quote-author {
          font-size: 12px;
          color: var(--ink-40);
          margin-top: 4px;
        }
      `}</style>
    </div>
  );
}
