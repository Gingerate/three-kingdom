import { useState, useEffect } from 'react';
import { Button, Tag, Spin, Empty, message, Table, Select, Checkbox, Card, Row, Col, Statistic } from 'antd';
import { CloudDownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { crawlPapers, getCrawlKeywords, getCrawlResults } from '../services/api';

interface Paper {
  title: string;
  authors: string[];
  year: number;
  abstract: string;
  keyword: string;
  citation_count: number;
}

export default function CrawlPage() {
  const [loading, setLoading] = useState(false);
  const [keywords, setKeywords] = useState<Record<string, string[]>>({});
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [maxPerKeyword, setMaxPerKeyword] = useState(3);
  const [downloadPdfs, setDownloadPdfs] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [papersLoading, setPapersLoading] = useState(false);

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
      width: 200,
      ellipsis: true,
      render: (authors: string[]) => authors?.join(', ') || '-',
    },
    {
      title: '年份',
      dataIndex: 'year',
      key: 'year',
      width: 80,
      align: 'center' as const,
    },
    {
      title: '引用',
      dataIndex: 'citation_count',
      key: 'citation_count',
      width: 80,
      align: 'center' as const,
      sorter: (a: Paper, b: Paper) => a.citation_count - b.citation_count,
    },
    {
      title: '关键词',
      dataIndex: 'keyword',
      key: 'keyword',
      width: 120,
      render: (keyword: string) => <Tag>{keyword}</Tag>,
    },
    {
      title: '摘要',
      dataIndex: 'abstract',
      key: 'abstract',
      ellipsis: true,
      render: (text: string) => (
        <span style={{ fontSize: 12, color: 'var(--ink-60)' }}>{text}</span>
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
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--r-md)',
          padding: 20,
          marginBottom: 20,
        }}>
          <h3 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 15,
            fontWeight: 700,
            color: 'var(--ink-100)',
            marginBottom: 14,
          }}>
            爬取配置
          </h3>

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
        </div>

        {/* 结果列表 */}
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--r-md)',
          padding: 20,
        }}>
          <h3 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 15,
            fontWeight: 700,
            color: 'var(--ink-100)',
            marginBottom: 14,
          }}>
            爬取结果
          </h3>

          {papers.length === 0 && !papersLoading ? (
            <Empty description="暂无论文数据" />
          ) : (
            <Table
              dataSource={papers}
              columns={columns}
              rowKey={(_, i) => String(i)}
              loading={papersLoading}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
