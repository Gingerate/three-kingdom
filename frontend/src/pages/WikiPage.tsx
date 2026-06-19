import { useState, useEffect, useRef } from 'react';
import { Button, Tag, Spin, message, Select, Popconfirm, Modal, Input } from 'antd';
import { BookOutlined, ThunderboltOutlined, DeleteOutlined, EditOutlined, ClearOutlined, SearchOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getWikiPages, getKnowledgeSummaries, distillWiki, deleteWikiPage, updateWikiPage, cleanupKnowledge } from '../services/api';
import EmptyState from '../components/EmptyState';

interface WikiPage {
  id: number;
  title: string;
  content: string;
  topic: string;
  source_sessions: string[];
  created_at: string;
}

interface KnowledgeSummary {
  id: number;
  session_id: string;
  question: string;
  summary: string;
  sources: string[];
  created_at: string;
}

export default function WikiPage() {
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [summaries, setSummaries] = useState<KnowledgeSummary[]>([]);
  const [selectedPage, setSelectedPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [distillLoading, setDistillLoading] = useState(false);
  const [view, setView] = useState<'list' | 'reader'>('list');
  const [topicFilter, setTopicFilter] = useState<string>('');
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editPage, setEditPage] = useState<WikiPage | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editTopic, setEditTopic] = useState('');
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    loadData();
  }, [topicFilter]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [wikiData, knowData] = await Promise.all([
        getWikiPages(topicFilter || undefined),
        getKnowledgeSummaries(50),
      ]);
      setPages(wikiData.pages || []);
      setSummaries(knowData.summaries || []);
    } catch {
      message.error('加载数据失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCleanupKnowledge = async () => {
    setCleanupLoading(true);
    try {
      const result = await cleanupKnowledge(30);
      message.success(`已清理 ${result.deleted_count} 条超过 30 天的知识摘要`);
      loadData();
    } catch {
      message.error('清理失败');
    } finally {
      setCleanupLoading(false);
    }
  };

  // 提取所有主题标签
  const topics = Array.from(new Set(pages.map(p => p.topic).filter(Boolean)));

  // 过滤页面
  const filteredPages = searchText
    ? pages.filter(p =>
        p.title.toLowerCase().includes(searchText.toLowerCase()) ||
        p.content.toLowerCase().includes(searchText.toLowerCase())
      )
    : pages;

  const handleDeletePage = async (pageId: number) => {
    try {
      await deleteWikiPage(pageId);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleEditPage = (page: WikiPage) => {
    setEditPage(page);
    setEditTitle(page.title);
    setEditContent(page.content);
    setEditTopic(page.topic || '');
    setEditModalVisible(true);
  };

  const handleSaveEdit = async () => {
    if (!editPage) return;
    try {
      await updateWikiPage(editPage.id, {
        title: editTitle,
        content: editContent,
        topic: editTopic,
      });
      message.success('更新成功');
      setEditModalVisible(false);
      loadData();
    } catch {
      message.error('更新失败');
    }
  };

  const handleDistill = async () => {
    setDistillLoading(true);
    try {
      const data = await distillWiki();
      if (data.status === 'ok') {
        message.success(`已生成 Wiki：${data.title}（${data.summary_count} 条摘要）`);
        loadData();
      } else {
        message.error(data.message || '生成失败');
      }
    } catch {
      message.error('生成 Wiki 失败');
    } finally {
      setDistillLoading(false);
    }
  };

  const openPage = (page: WikiPage) => {
    setSelectedPage(page);
    setView('reader');
  };

  const closePage = () => {
    setSelectedPage(null);
    setView('list');
  };

  if (view === 'reader' && selectedPage) {
    return <WikiReader page={selectedPage} onClose={closePage} />;
  }

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">知识沉淀</span>
        <Tag style={{ fontSize: 11 }}>{summaries.length} 条摘要</Tag>
        <Tag style={{ fontSize: 11 }}>{filteredPages.length} 篇 Wiki</Tag>
        <Input
          placeholder="搜索 Wiki"
          prefix={<SearchOutlined style={{ color: 'var(--color-ink-4)' }} />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          allowClear
          style={{ width: 160 }}
          size="small"
        />
        <Select
          placeholder="按主题筛选"
          allowClear
          style={{ width: 120 }}
          value={topicFilter || undefined}
          onChange={(v) => setTopicFilter(v || '')}
          options={topics.map(t => ({ value: t, label: t }))}
          size="small"
        />
        <div className="page-header-spacer" />
        <Popconfirm
          title="确定清理超过 30 天的知识摘要？"
          onConfirm={handleCleanupKnowledge}
        >
          <Button
            icon={<ClearOutlined />}
            loading={cleanupLoading}
            size="small"
          >
            清理旧摘要
          </Button>
        </Popconfirm>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={handleDistill}
          loading={distillLoading}
          disabled={summaries.length === 0}
          size="small"
        >
          生成 Wiki
        </Button>
      </div>

      {/* 内容 */}
      <div className="page-body">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 80 }}>
            <Spin size="large" />
          </div>
        ) : (
          <>
            {/* Wiki 页面列表 */}
            {filteredPages.length > 0 && (
              <div style={{ marginBottom: 32 }}>
                <h3 style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 16,
                  fontWeight: 700,
                  color: 'var(--color-ink)',
                  marginBottom: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}>
                  <BookOutlined />
                  Wiki 页面
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
                  {filteredPages.map((page) => (
                    <div
                      key={page.id}
                      className="wiki-card"
                    >
                      <div onClick={() => openPage(page)} style={{ cursor: 'pointer' }}>
                        <div style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: 15,
                          fontWeight: 700,
                          color: 'var(--color-ink)',
                          marginBottom: 8,
                        }}>
                          {page.title}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--color-ink-4)', marginBottom: 8 }}>
                          {new Date(page.created_at).toLocaleDateString('zh-CN')}
                          {page.topic && <Tag style={{ marginLeft: 8, fontSize: 11 }}>{page.topic}</Tag>}
                        </div>
                        <div style={{
                          fontSize: 13,
                          color: 'var(--color-ink-3)',
                          lineHeight: 1.6,
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}>
                          {(page.content || '').replace(/[#*\-]/g, '').slice(0, 150)}...
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 8, justifyContent: 'flex-end' }}>
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(e) => { e.stopPropagation(); handleEditPage(page); }}
                        />
                        <Popconfirm
                          title="确定删除此 Wiki 页面？"
                          onConfirm={(e) => { e?.stopPropagation(); handleDeletePage(page.id); }}
                          onCancel={(e) => e?.stopPropagation()}
                        >
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Popconfirm>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 最近摘要 */}
            <div>
              <h3 style={{
                fontFamily: 'var(--font-display)',
                fontSize: 16,
                fontWeight: 700,
                color: 'var(--color-ink)',
                marginBottom: 16,
              }}>
                最近知识摘要
              </h3>
              {summaries.length === 0 ? (
                <EmptyState
                  icon={<BookOutlined />}
                  title="暂无摘要"
                  description="开始对话后自动提取知识摘要"
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {summaries.slice(0, 20).map((s) => (
                    <div
                      key={s.id}
                      style={{
                        background: 'var(--color-paper-2)',
                        border: '1px solid var(--color-rule-2)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '12px 16px',
                      }}
                    >
                      <div style={{ fontSize: 12, color: 'var(--color-ink-4)', marginBottom: 4 }}>
                        问：{s.question}
                      </div>
                      <div style={{ fontSize: 14, color: 'var(--color-ink-2)', lineHeight: 1.7 }}>
                        {s.summary}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {pages.length === 0 && summaries.length === 0 && (
              <EmptyState
                icon={<BookOutlined />}
                title="暂无知识内容"
                description="开始智能问答后，系统会自动提取知识摘要。积累足够摘要后，可生成 Wiki 页面。"
              />
            )}
          </>
        )}
      </div>

      {/* 编辑 Modal */}
      <Modal
        title="编辑 Wiki 页面"
        open={editModalVisible}
        onOk={handleSaveEdit}
        onCancel={() => setEditModalVisible(false)}
        width={800}
        okText="保存"
        cancelText="取消"
        className="themed-modal"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ fontSize: 13, color: 'var(--color-ink-3)', marginBottom: 4, display: 'block' }}>标题</label>
            <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 13, color: 'var(--color-ink-3)', marginBottom: 4, display: 'block' }}>主题标签</label>
            <Input value={editTopic} onChange={(e) => setEditTopic(e.target.value)} placeholder="如：人物、战役、制度" />
          </div>
          <div>
            <label style={{ fontSize: 13, color: 'var(--color-ink-3)', marginBottom: 4, display: 'block' }}>内容 (Markdown)</label>
            <Input.TextArea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={15}
              style={{ fontFamily: 'monospace' }}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}


/* ── Wiki 阅读器 ── */

interface TocItem {
  idx: number;
  level: number;
  text: string;
}

function WikiReader({ page, onClose }: {
  page: WikiPage;
  onClose: () => void;
}) {
  const [visibleSections, setVisibleSections] = useState<Set<number>>(new Set());
  const [activeIdx, setActiveIdx] = useState(0);
  const [scrollProgress, setScrollProgress] = useState(0);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);
  const contentRef = useRef<HTMLDivElement>(null);

  // 将内容按 h2 分段
  const sections = page.content.split(/(?=^## )/m).filter(Boolean);

  // 提取目录结构
  const tocItems: TocItem[] = sections.map((section, idx) => {
    const firstLine = section.split('\n')[0];
    const match = firstLine.match(/^(#{2,3})\s+(.+)/);
    return match ? { idx, level: match[1].length, text: match[2].trim() } : { idx, level: 2, text: `段落 ${idx + 1}` };
  });

  useEffect(() => {
    // 为每个 h2 段落设置 IntersectionObserver
    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const idx = parseInt(entry.target.getAttribute('data-idx') || '0');
          if (entry.isIntersecting) {
            setVisibleSections((prev) => new Set([...prev, idx]));
            setActiveIdx(idx);
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -50px 0px' }
    );

    sectionRefs.current.forEach((el) => {
      if (el) observerRef.current?.observe(el);
    });

    return () => observerRef.current?.disconnect();
  }, []);

  // 监听滚动进度
  useEffect(() => {
    const container = contentRef.current;
    if (!container) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const progress = scrollHeight > clientHeight
        ? (scrollTop / (scrollHeight - clientHeight)) * 100
        : 0;
      setScrollProgress(Math.min(100, Math.max(0, progress)));
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // 点击目录跳转
  const scrollToSection = (idx: number) => {
    const el = sectionRefs.current[idx];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="page-shell wiki-reader" style={{ background: 'var(--color-paper)' }}>
      {/* 阅读进度条 */}
      <div className="wiki-progress-bar">
        <div
          className="wiki-progress-fill"
          style={{ width: `${scrollProgress}%` }}
        />
      </div>

      {/* 顶栏 */}
      <div className="page-header" style={{ position: 'relative', zIndex: 2 }}>
        <Button type="text" size="small" onClick={onClose} style={{ color: 'var(--color-ink-3)' }}>
          ← 返回
        </Button>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, color: 'var(--color-ink)' }}>
          {page.title}
        </div>
        {page.topic && <Tag style={{ fontSize: 11 }}>{page.topic}</Tag>}
        <div className="page-header-spacer" />
        <Button size="small" onClick={() => window.print()}>
          打印 / PDF
        </Button>
        <span style={{ fontSize: 12, color: 'var(--color-ink-4)' }}>
          {new Date(page.created_at).toLocaleDateString('zh-CN')}
        </span>
      </div>

      {/* 浮动目录 */}
      <nav className="wiki-toc" aria-label="文章目录">
        <div className="wiki-toc-title">目录</div>
        {tocItems.map((item) => (
          <button
            key={item.idx}
            className={`wiki-toc-item ${activeIdx === item.idx ? 'active' : ''} ${item.level === 3 ? 'sub' : ''}`}
            onClick={() => scrollToSection(item.idx)}
          >
            {item.text}
          </button>
        ))}
      </nav>

      {/* 阅读区 */}
      <div ref={contentRef} style={{ flex: 1, overflow: 'auto', padding: '0', position: 'relative', zIndex: 1 }}>
        {/* 标题区 — 卷轴头部 */}
        <div style={{
          padding: '56px 40px 40px',
          textAlign: 'center',
          borderBottom: '1px solid var(--color-rule)',
          background: 'linear-gradient(180deg, var(--color-paper-2) 0%, var(--color-paper) 100%)',
          position: 'relative',
        }}>
          {page.topic && (
            <div style={{
              fontSize: 11,
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              color: 'var(--color-accent)',
              letterSpacing: 3,
              textTransform: 'uppercase',
              marginBottom: 12,
              opacity: 0.7,
            }}>
              {page.topic}
            </div>
          )}
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 30,
            fontWeight: 700,
            color: 'var(--color-ink)',
            letterSpacing: 5,
            marginBottom: 16,
            lineHeight: 1.3,
          }}>
            {page.title}
          </h1>
          <div style={{
            width: 24,
            height: 1,
            background: 'var(--color-accent)',
            margin: '0 auto 12px',
            opacity: 0.5,
          }} />
          <div style={{ fontSize: 13, color: 'var(--color-ink-4)', letterSpacing: 1 }}>
            {new Date(page.created_at).toLocaleDateString('zh-CN', {
              year: 'numeric', month: 'long', day: 'numeric',
            })}
          </div>
        </div>

        {/* 内容段落 — 逐段入场 */}
        <div className="wiki-content" style={{ maxWidth: 680, margin: '0 auto', padding: '40px 24px 100px' }}>
          {sections.map((section, idx) => {
            const isVisible = visibleSections.has(idx);
            return (
              <div
                key={idx}
                ref={(el) => { sectionRefs.current[idx] = el; }}
                data-idx={idx}
                className="wiki-section"
                style={{
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? 'translateY(0)' : 'translateY(16px)',
                  filter: isVisible ? 'blur(0)' : 'blur(1.5px)',
                  transition: 'opacity 0.7s var(--ease-out), transform 0.7s var(--ease-out), filter 0.7s var(--ease-out)',
                  marginBottom: 40,
                }}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: ({ children }) => <h1 className="wiki-h1">{children}</h1>,
                    h2: ({ children }) => <h2 className="wiki-h2">{children}</h2>,
                    h3: ({ children }) => <h3 className="wiki-h3">{children}</h3>,
                    p: ({ children }) => <p className="wiki-p">{children}</p>,
                    ul: ({ children }) => <ul className="wiki-ul">{children}</ul>,
                    ol: ({ children }) => <ol className="wiki-ol">{children}</ol>,
                    li: ({ children }) => <li className="wiki-li">{children}</li>,
                    hr: () => <hr className="wiki-hr" />,
                    pre: ({ children }) => <pre className="wiki-pre">{children}</pre>,
                    code: ({ children, className }) => {
                      const isInline = !className;
                      return isInline
                        ? <code className="wiki-code">{children}</code>
                        : <code>{children}</code>;
                    },
                    strong: ({ children }) => <strong>{children}</strong>,
                    em: ({ children }) => <em>{children}</em>,
                  }}
                >
                  {section}
                </ReactMarkdown>
              </div>
            );
          })}
        </div>
      </div>

      {/* 全局样式注入 */}
      <style>{`
        .wiki-h1 {
          font-family: var(--font-display);
          font-size: 26px;
          font-weight: 700;
          color: var(--color-ink);
          margin: 48px 0 20px;
          letter-spacing: 3px;
          border-left: 3px solid var(--color-accent);
          padding-left: 14px;
        }
        .wiki-h2 {
          font-family: var(--font-display);
          font-size: 19px;
          font-weight: 700;
          color: var(--color-ink);
          margin: 44px 0 16px;
          letter-spacing: 1.5px;
          padding-bottom: 10px;
          border-bottom: 1px solid var(--color-rule-2);
        }
        .wiki-h3 {
          font-family: var(--font-display);
          font-size: 15px;
          font-weight: 700;
          color: var(--color-ink-2);
          margin: 28px 0 10px;
          letter-spacing: 0.5px;
        }
        .wiki-p {
          font-size: 15px;
          line-height: 2;
          color: var(--color-ink-2);
          margin: 20px 0;
          text-align: justify;
          text-indent: 0;
        }
        .wiki-li {
          font-size: 15px;
          line-height: 2;
          color: var(--color-ink-2);
          margin: 8px 0 8px 20px;
          list-style: disc;
        }
        .wiki-hr {
          border: none;
          height: 1px;
          background: var(--color-rule);
          margin: 40px 0;
          position: relative;
        }
        .wiki-hr::after {
          content: '◆';
          position: absolute;
          left: 50%;
          top: -8px;
          transform: translateX(-50%);
          background: var(--color-paper);
          padding: 0 12px;
          color: var(--color-ink-5);
          font-size: 12px;
        }
        .wiki-p strong {
          color: var(--color-ink);
          font-weight: 600;
          letter-spacing: 0.3px;
        }
        .wiki-pre {
          background: var(--color-paper);
          border: 1px solid var(--color-rule);
          border-radius: var(--radius-sm);
          padding: 12px 16px;
          overflow-x: auto;
          margin: 12px 0;
        }
        .wiki-pre code {
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 13px;
          color: var(--color-ink-2);
        }
        .wiki-code {
          background: var(--color-paper);
          border: 1px solid var(--color-rule);
          border-radius: 3px;
          padding: 1px 6px;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 0.9em;
          color: var(--color-accent);
        }
        .wiki-ul, .wiki-ol {
          margin: 8px 0;
          padding-left: 24px;
        }
        .wiki-li-ordered {
          font-size: 15px;
          line-height: 2;
          color: var(--color-ink-2);
          margin: 4px 0;
        }
        .wiki-p em {
          font-style: italic;
          color: var(--color-ink-3);
        }

        /* 浮动目录 */
        .wiki-reader {
          display: flex;
          flex-direction: column;
          position: relative;
        }

        /* 极微纸张噪点 — 暗示纸张温度，不做拟真纹理 */
        .wiki-reader::before {
          content: '';
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 0;
          opacity: 0.018;
          filter: url(#paper-noise);
          background: var(--color-paper);
        }

        .wiki-reader::after {
          content: '';
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 0;
          opacity: 0.015;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
          background-size: 256px 256px;
        }

        .wiki-toc {
          position: fixed;
          left: 24px;
          top: 100px;
          width: 180px;
          max-height: calc(100vh - 160px);
          overflow-y: auto;
          z-index: 10;
          display: flex;
          flex-direction: column;
          padding-left: 16px;
          border-left: 1px solid var(--color-rule);
        }

        .wiki-toc-title {
          font-family: var(--font-display);
          font-size: 11px;
          font-weight: 700;
          color: var(--color-ink-4);
          letter-spacing: 3px;
          text-transform: uppercase;
          margin-bottom: 14px;
          padding: 0;
        }

        .wiki-toc-item {
          display: block;
          width: 100%;
          text-align: left;
          background: none;
          border: none;
          cursor: pointer;
          font-family: var(--font-display);
          font-size: 13px;
          font-weight: 400;
          color: var(--color-ink-4);
          padding: 6px 12px 6px 0;
          margin-left: -1px;
          border-left: 2px solid transparent;
          transition: color var(--dur-fast) var(--ease-out),
                      border-color var(--dur-fast) var(--ease-out);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          line-height: 1.4;
        }

        .wiki-toc-item.sub {
          padding-left: 14px;
          font-size: 12px;
          font-weight: 300;
          color: var(--color-ink-5);
        }

        .wiki-toc-item:hover {
          color: var(--color-ink-2);
        }

        .wiki-toc-item.active {
          color: var(--color-accent);
          border-left-color: var(--color-accent);
          font-weight: 600;
        }

        .wiki-toc-item.sub.active {
          font-weight: 500;
        }

        /* 隐藏滚动条但保留功能 */
        .wiki-toc::-webkit-scrollbar {
          width: 0;
        }

        /* 小屏幕隐藏目录 */
        @media (max-width: 1200px) {
          .wiki-toc {
            display: none;
          }
        }

        /* 阅读进度条 */
        .wiki-progress-bar {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: var(--color-rule-2);
          z-index: 1000;
        }

        .wiki-progress-fill {
          height: 100%;
          background: var(--color-accent);
          transition: width 0.1s linear;
          border-radius: 0 2px 2px 0;
        }

        /* 打印样式 */
        @media print {
          .page-header,
          .wiki-toc,
          .wiki-progress-bar,
          .topbar,
          .ink-landscape {
            display: none !important;
          }

          .wiki-reader::before,
          .wiki-reader::after {
            display: none !important;
          }

          .page-shell {
            background: white !important;
          }

          .wiki-content {
            max-width: 100% !important;
            padding: 0 !important;
          }

          .wiki-section {
            opacity: 1 !important;
            transform: none !important;
            filter: none !important;
            break-inside: avoid;
          }

          .wiki-h1 {
            border-left: 3px solid #1a1a1a !important;
          }

          .wiki-hr::after {
            background: white !important;
          }

          body {
            overflow: visible !important;
          }

          #root {
            height: auto !important;
            overflow: visible !important;
          }
        }
      `}</style>
    </div>
  );
}
