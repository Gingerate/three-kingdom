import { useState, useEffect, useRef } from 'react';
import { Button, Tag, Spin, Empty, message, Select, Popconfirm, Modal, Input, Statistic, Row, Col } from 'antd';
import { BookOutlined, ThunderboltOutlined, DeleteOutlined, EditOutlined, ClearOutlined } from '@ant-design/icons';
import { getWikiPages, getKnowledgeSummaries, distillWiki, deleteWikiPage, updateWikiPage, getKnowledgeStats, cleanupKnowledge } from '../services/api';

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
  const [knowledgeStats, setKnowledgeStats] = useState<{ total: number; oldest: string; newest: string } | null>(null);
  const [cleanupLoading, setCleanupLoading] = useState(false);

  useEffect(() => {
    loadData();
  }, [topicFilter]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [wikiData, knowData, stats] = await Promise.all([
        getWikiPages(topicFilter || undefined),
        getKnowledgeSummaries(50),
        getKnowledgeStats(),
      ]);
      setPages(wikiData.pages || []);
      setSummaries(knowData.summaries || []);
      setKnowledgeStats(stats);
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

  // 转义 HTML 特殊字符，防止 XSS
  const escapeHtml = (text: string) => {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  };

  // Markdown → HTML（简化版，支持标题、加粗、列表、分割线、代码块、有序列表）
  const renderMarkdown = (md: string) => {
    // 先转义 HTML 特殊字符
    let html = escapeHtml(md);

    // 代码块（```...```）
    html = html.replace(/```[\s\S]*?```/g, (match) => {
      const code = match.slice(3, -3).trim();
      return `<pre class="wiki-pre"><code>${code}</code></pre>`;
    });

    // 行内代码（`...`）
    html = html.replace(/`([^`]+)`/g, '<code class="wiki-code">$1</code>');

    // 标题
    html = html.replace(/^# (.+)$/gm, '<h1 class="wiki-h1">$1</h1>');
    html = html.replace(/^## (.+)$/gm, '<h2 class="wiki-h2">$1</h2>');
    html = html.replace(/^### (.+)$/gm, '<h3 class="wiki-h3">$1</h3>');

    // 加粗和斜体
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 无序列表
    html = html.replace(/^\- (.+)$/gm, '<li class="wiki-li">$1</li>');

    // 有序列表
    html = html.replace(/^\d+\.\s+(.+)$/gm, '<li class="wiki-li-ordered">$1</li>');

    // 分割线
    html = html.replace(/^---$/gm, '<hr class="wiki-hr" />');

    // 段落（非标签开头的行）
    html = html.replace(/^(?!<[hlp]|<li|<hr|<pre|<code)(.+)$/gm, '<p class="wiki-p">$1</p>');

    // 合并连续的列表项
    html = html.replace(/(<li class="wiki-li">[\s\S]*?<\/li>)/g, '<ul class="wiki-ul">$1</ul>');
    html = html.replace(/(<li class="wiki-li-ordered">[\s\S]*?<\/li>)/g, '<ol class="wiki-ol">$1</ol>');

    return html;
  };

  if (view === 'reader' && selectedPage) {
    return <WikiReader page={selectedPage} onClose={closePage} renderMarkdown={renderMarkdown} />;
  }

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">知识沉淀</span>
        <Tag style={{ fontSize: 11 }}>{summaries.length} 条摘要</Tag>
        <Tag style={{ fontSize: 11 }}>{pages.length} 篇 Wiki</Tag>
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
            {pages.length > 0 && (
              <div style={{ marginBottom: 32 }}>
                <h3 style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 16,
                  fontWeight: 700,
                  color: 'var(--ink-100)',
                  marginBottom: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}>
                  <BookOutlined />
                  Wiki 页面
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
                  {pages.map((page) => (
                    <div
                      key={page.id}
                      className="wiki-card"
                    >
                      <div onClick={() => openPage(page)} style={{ cursor: 'pointer' }}>
                        <div style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: 15,
                          fontWeight: 700,
                          color: 'var(--ink-100)',
                          marginBottom: 8,
                        }}>
                          {page.title}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--ink-40)', marginBottom: 8 }}>
                          {new Date(page.created_at).toLocaleDateString('zh-CN')}
                          {page.topic && <Tag style={{ marginLeft: 8, fontSize: 11 }}>{page.topic}</Tag>}
                        </div>
                        <div style={{
                          fontSize: 13,
                          color: 'var(--ink-60)',
                          lineHeight: 1.6,
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}>
                          {(page.content || page.content_preview || '').replace(/[#*\-]/g, '').slice(0, 150)}...
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
                color: 'var(--ink-100)',
                marginBottom: 16,
              }}>
                最近知识摘要
              </h3>
              {summaries.length === 0 ? (
                <Empty description="暂无摘要，开始对话后自动提取" />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {summaries.slice(0, 20).map((s) => (
                    <div
                      key={s.id}
                      style={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-faint)',
                        borderRadius: 'var(--r-sm)',
                        padding: '12px 16px',
                      }}
                    >
                      <div style={{ fontSize: 12, color: 'var(--ink-40)', marginBottom: 4 }}>
                        问：{s.question}
                      </div>
                      <div style={{ fontSize: 14, color: 'var(--ink-80)', lineHeight: 1.7 }}>
                        {s.summary}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {pages.length === 0 && summaries.length === 0 && (
              <div style={{ textAlign: 'center', padding: 60, color: 'var(--ink-40)' }}>
                <BookOutlined style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }} />
                <p>开始智能问答后，系统会自动提取知识摘要</p>
                <p style={{ fontSize: 13 }}>积累足够摘要后，可生成 Wiki 页面</p>
              </div>
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
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ fontSize: 13, color: 'var(--ink-60)', marginBottom: 4, display: 'block' }}>标题</label>
            <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 13, color: 'var(--ink-60)', marginBottom: 4, display: 'block' }}>主题标签</label>
            <Input value={editTopic} onChange={(e) => setEditTopic(e.target.value)} placeholder="如：人物、战役、制度" />
          </div>
          <div>
            <label style={{ fontSize: 13, color: 'var(--ink-60)', marginBottom: 4, display: 'block' }}>内容 (Markdown)</label>
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

function WikiReader({ page, onClose, renderMarkdown }: {
  page: WikiPage;
  onClose: () => void;
  renderMarkdown: (md: string) => string;
}) {
  const [visibleSections, setVisibleSections] = useState<Set<number>>(new Set());
  const observerRef = useRef<IntersectionObserver | null>(null);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 为每个 h2 段落设置 IntersectionObserver
    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const idx = parseInt(entry.target.getAttribute('data-idx') || '0');
          if (entry.isIntersecting) {
            setVisibleSections((prev) => new Set([...prev, idx]));
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

  // 将内容按 h2 分段
  const sections = page.content.split(/(?=^## )/m).filter(Boolean);

  return (
    <div className="page-shell" style={{ background: 'var(--bg-base)' }}>
      {/* 顶栏 */}
      <div className="page-header">
        <Button type="text" size="small" onClick={onClose} style={{ color: 'var(--ink-60)' }}>
          ← 返回
        </Button>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, color: 'var(--ink-100)' }}>
          {page.title}
        </div>
        {page.topic && <Tag style={{ fontSize: 11 }}>{page.topic}</Tag>}
        <div className="page-header-spacer" />
        <span style={{ fontSize: 12, color: 'var(--ink-40)' }}>
          {new Date(page.created_at).toLocaleDateString('zh-CN')}
        </span>
      </div>

      {/* 阅读区 */}
      <div ref={contentRef} style={{ flex: 1, overflow: 'auto', padding: '0' }}>
        {/* 标题区 — 卷轴头部 */}
        <div style={{
          padding: '60px 40px 40px',
          textAlign: 'center',
          borderBottom: '2px solid var(--vermilion)',
          background: 'linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-base) 100%)',
          position: 'relative',
        }}>
          {/* 装饰竖线 */}
          <div style={{
            position: 'absolute',
            left: '50%',
            top: 30,
            transform: 'translateX(-50%)',
            width: 2,
            height: 20,
            background: 'var(--vermilion)',
          }} />
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 28,
            fontWeight: 700,
            color: 'var(--ink-100)',
            letterSpacing: 4,
            marginBottom: 12,
          }}>
            {page.title}
          </h1>
          <div style={{ fontSize: 13, color: 'var(--ink-40)' }}>
            {new Date(page.created_at).toLocaleDateString('zh-CN', {
              year: 'numeric', month: 'long', day: 'numeric',
            })}
          </div>
        </div>

        {/* 内容段落 — 逐段入场 */}
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 24px 80px' }}>
          {sections.map((section, idx) => {
            const isVisible = visibleSections.has(idx);
            return (
              <div
                key={idx}
                ref={(el) => { sectionRefs.current[idx] = el; }}
                data-idx={idx}
                style={{
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
                  filter: isVisible ? 'blur(0)' : 'blur(4px)',
                  transition: 'all 0.8s cubic-bezier(0.22, 1, 0.36, 1)',
                  marginBottom: 32,
                }}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(section) }}
              />
            );
          })}
        </div>
      </div>

      {/* 全局样式注入 */}
      <style>{`
        .wiki-h1 {
          font-family: var(--font-display);
          font-size: 24px;
          font-weight: 700;
          color: var(--ink-100);
          margin: 32px 0 16px;
          letter-spacing: 2px;
          border-left: 3px solid var(--vermilion);
          padding-left: 12px;
        }
        .wiki-h2 {
          font-family: var(--font-display);
          font-size: 18px;
          font-weight: 700;
          color: var(--ink-100);
          margin: 28px 0 12px;
          letter-spacing: 1px;
        }
        .wiki-h3 {
          font-family: var(--font-display);
          font-size: 15px;
          font-weight: 700;
          color: var(--ink-80);
          margin: 20px 0 8px;
        }
        .wiki-p {
          font-size: 15px;
          line-height: 2;
          color: var(--ink-80);
          margin: 8px 0;
          text-align: justify;
        }
        .wiki-li {
          font-size: 15px;
          line-height: 2;
          color: var(--ink-80);
          margin: 4px 0 4px 20px;
          list-style: disc;
        }
        .wiki-hr {
          border: none;
          height: 1px;
          background: var(--border);
          margin: 32px 0;
          position: relative;
        }
        .wiki-hr::after {
          content: '◆';
          position: absolute;
          left: 50%;
          top: -8px;
          transform: translateX(-50%);
          background: var(--bg-base);
          padding: 0 12px;
          color: var(--ink-20);
          font-size: 12px;
        }
        .wiki-p strong {
          color: var(--ink-100);
          font-weight: 700;
        }
        .wiki-pre {
          background: var(--bg-base);
          border: 1px solid var(--border);
          border-radius: var(--r-sm);
          padding: 12px 16px;
          overflow-x: auto;
          margin: 12px 0;
        }
        .wiki-pre code {
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 13px;
          color: var(--ink-80);
        }
        .wiki-code {
          background: var(--bg-base);
          border: 1px solid var(--border);
          border-radius: 3px;
          padding: 1px 6px;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 0.9em;
          color: var(--vermilion);
        }
        .wiki-ul, .wiki-ol {
          margin: 8px 0;
          padding-left: 24px;
        }
        .wiki-li-ordered {
          font-size: 15px;
          line-height: 2;
          color: var(--ink-80);
          margin: 4px 0;
        }
        .wiki-p em {
          font-style: italic;
          color: var(--ink-60);
        }
      `}</style>
    </div>
  );
}
