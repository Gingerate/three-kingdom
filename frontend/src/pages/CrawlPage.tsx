import { useState, useEffect } from 'react';
import { Button, Tag, message, Table, Select, Checkbox, Modal, Space, Popconfirm } from 'antd';
import {
  CloudDownloadOutlined,
  ReloadOutlined,
  BookOutlined,
  LinkOutlined,
  DeleteOutlined,
  ImportOutlined,
  EyeOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import {
  crawlPapers,
  getCrawlKeywords,
  getCrawlResults,
  deleteCrawlResult,
  ingestCrawlResult,
} from '../services/api';
import Section from './data/Section';
import EmptyState from '../components/EmptyState';

interface Paper {
  title: string;
  authors: string[];
  year: number;
  abstract: string;
  keyword: string;
  citation_count: number;
  url?: string;
  pdf_url?: string;
  source?: string;
}

export default function CrawlPage() {
  const [loading, setLoading] = useState(false);
  const [keywords, setKeywords] = useState<Record<string, string[]>>({});
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [maxPerKeyword, setMaxPerKeyword] = useState(3);
  const [downloadPdfs, setDownloadPdfs] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [papersLoading, setPapersLoading] = useState(false);

  // 详情弹窗
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);

  useEffect(() => {
    loadKeywords();
    loadResults();
  }, []);

  const loadKeywords = async () => {
    try {
      const data = await getCrawlKeywords();
      setKeywords(data);
    } catch {
      message.error('加载关键词失败');
    }
  };

  const loadResults = async () => {
    setPapersLoading(true);
    try {
      const data = await getCrawlResults();
      setPapers(data.papers || []);
    } catch {
      message.error('加载结果失败');
    } finally {
      setPapersLoading(false);
    }
  };

  const handleCrawl = async () => {
    setLoading(true);
    try {
      const result = await crawlPapers({
        categories: selectedCategories.length > 0 ? selectedCategories : undefined,
        max_per_keyword: maxPerKeyword,
        download_pdfs: downloadPdfs,
      });
      message.success(`爬取完成，获取 ${result.result?.papers_count || 0} 篇论文`);
      loadResults();
    } catch {
      message.error('爬取失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (index: number) => {
    try {
      await deleteCrawlResult(index);
      message.success('删除成功');
      loadResults();
    } catch {
      message.error('删除失败');
    }
  };

  const handleIngest = async (index: number) => {
    try {
      const result = await ingestCrawlResult(index);
      message.success(result.message || '导入成功');
    } catch {
      message.error('导入失败');
    }
  };

  const handleViewDetail = (paper: Paper) => {
    setSelectedPaper(paper);
    setDetailModalVisible(true);
  };

  const handleOpenUrl = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const categories = Object.keys(keywords);

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text: string) => (
        <span style={{ fontWeight: 600 }}>{text}</span>
      ),
    },
    {
      title: '作者',
      dataIndex: 'authors',
      key: 'authors',
      width: 180,
      ellipsis: true,
      render: (authors: string[]) => authors?.join(', ') || '-',
    },
    {
      title: '年份',
      dataIndex: 'year',
      key: 'year',
      width: 70,
      align: 'center' as const,
    },
    {
      title: '引用',
      dataIndex: 'citation_count',
      key: 'citation_count',
      width: 70,
      align: 'center' as const,
      sorter: (a: Paper, b: Paper) => a.citation_count - b.citation_count,
    },
    {
      title: '关键词',
      dataIndex: 'keyword',
      key: 'keyword',
      width: 100,
      render: (keyword: string) => <Tag>{keyword}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: Paper, index: number) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            详情
          </Button>
          {record.url && (
            <Button
              size="small"
              icon={<LinkOutlined />}
              onClick={() => handleOpenUrl(record.url!)}
            >
              原文
            </Button>
          )}
          <Popconfirm
            title="确定导入此论文到知识库？"
            onConfirm={() => handleIngest(index)}
          >
            <Button size="small" icon={<ImportOutlined />}>
              入库
            </Button>
          </Popconfirm>
          <Popconfirm
            title="确定删除此论文？"
            onConfirm={() => handleDelete(index)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">论文爬虫</span>
        <Tag style={{ fontSize: 11 }}>{papers.length} 篇论文</Tag>
        <div className="page-header-spacer" />
        <Button icon={<ReloadOutlined />} onClick={loadResults} loading={papersLoading} size="small">
          刷新
        </Button>
      </div>

      {/* 内容 */}
      <div className="page-body">
        {/* 配置区 */}
        <Section title="爬取配置">

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--ink-60)', marginBottom: 8 }}>选择类别（不选则全部）</div>
            <Select
              mode="multiple"
              placeholder="选择类别"
              style={{ width: '100%' }}
              value={selectedCategories}
              onChange={setSelectedCategories}
              options={categories.map(c => ({ value: c, label: c }))}
            />
          </div>

          {selectedCategories.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: 'var(--ink-60)', marginBottom: 8 }}>关键词预览</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {selectedCategories.flatMap(cat => keywords[cat] || []).map(kw => (
                  <Tag key={kw} style={{ fontSize: 11 }}>{kw}</Tag>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: 13, color: 'var(--ink-60)', marginRight: 8 }}>每关键词最大数量：</span>
              <Select
                value={maxPerKeyword}
                onChange={setMaxPerKeyword}
                style={{ width: 80 }}
                options={[
                  { value: 1, label: '1' },
                  { value: 3, label: '3' },
                  { value: 5, label: '5' },
                  { value: 10, label: '10' },
                ]}
              />
            </div>
            <Checkbox
              checked={downloadPdfs}
              onChange={(e) => setDownloadPdfs(e.target.checked)}
            >
              下载 PDF
            </Checkbox>
            <Button
              type="primary"
              icon={<CloudDownloadOutlined />}
              onClick={handleCrawl}
              loading={loading}
            >
              开始爬取
            </Button>
          </div>
        </Section>

        {/* 结果列表 */}
        <Section title="爬取结果">
          {papers.length === 0 && !papersLoading ? (
            <EmptyState
              icon={<BookOutlined />}
              title="暂无论文数据"
              description="配置爬取参数后点击「开始爬取」"
            />
          ) : (
            <div className="themed-table">
              <Table
                dataSource={papers}
                columns={columns}
                rowKey={(_, i) => String(i)}
                loading={papersLoading}
                size="small"
                pagination={{ pageSize: 10 }}
              />
            </div>
          )}
        </Section>
      </div>

      {/* 论文详情弹窗 */}
      <Modal
        title="论文详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>,
          selectedPaper?.url && (
            <Button
              key="link"
              type="primary"
              icon={<LinkOutlined />}
              onClick={() => handleOpenUrl(selectedPaper.url!)}
            >
              打开原文
            </Button>
          ),
          selectedPaper?.pdf_url && (
            <Button
              key="pdf"
              icon={<FileTextOutlined />}
              onClick={() => handleOpenUrl(selectedPaper.pdf_url!)}
            >
              下载 PDF
            </Button>
          ),
        ]}
        width={700}
        className="themed-modal"
      >
        {selectedPaper && (
          <div style={{ lineHeight: 1.8 }}>
            <h3 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18,
              fontWeight: 700,
              color: 'var(--ink-100)',
              marginBottom: 16,
            }}>
              {selectedPaper.title}
            </h3>

            <div style={{ marginBottom: 16 }}>
              <Tag color="blue">{selectedPaper.keyword}</Tag>
              {selectedPaper.source && <Tag>{selectedPaper.source}</Tag>}
              {selectedPaper.year && <Tag>{selectedPaper.year}年</Tag>}
              {selectedPaper.citation_count > 0 && (
                <Tag color="orange">引用 {selectedPaper.citation_count}</Tag>
              )}
            </div>

            <div style={{ marginBottom: 16, color: 'var(--ink-80)' }}>
              <strong>作者：</strong>
              {selectedPaper.authors?.join('、') || '未知'}
            </div>

            <div style={{
              background: 'var(--bg-sunken)',
              padding: 16,
              borderRadius: 'var(--r-md)',
              marginBottom: 16,
            }}>
              <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--ink-100)' }}>
                摘要
              </div>
              <div style={{ color: 'var(--ink-80)', textAlign: 'justify' }}>
                {selectedPaper.abstract || '暂无摘要'}
              </div>
            </div>

            {selectedPaper.url && (
              <div style={{ fontSize: 13, color: 'var(--ink-60)' }}>
                <strong>原文链接：</strong>
                <a
                  href={selectedPaper.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--vermilion)', marginLeft: 8 }}
                >
                  {selectedPaper.url}
                </a>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
