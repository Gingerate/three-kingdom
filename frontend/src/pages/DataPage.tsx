import { useState, useEffect, useRef, useMemo } from 'react';
import { Upload, Button, Checkbox, message, Table, Popconfirm, Input, Select, Drawer, Space, Tag } from 'antd';
import { InboxOutlined, SyncOutlined, DatabaseOutlined, FileTextOutlined, CloudUploadOutlined, DeleteOutlined, ClearOutlined, ReloadOutlined, SearchOutlined, SwapOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import InkProgress from '../components/InkProgress';
const API_BASE = 'http://localhost:8000/api';

interface IngestionFile {
  source_file: string;
  chunk_count: number;
  first_ingested: string;
  last_ingested: string;
}

interface RawFile {
  filename: string;
  filepath: string;
  size: number;
  modified: number;
  file_type: string;
  status: string;
  suffix: string;
}

export default function DataPage() {
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<{ count: number; collection_name: string } | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState<'active' | 'success' | 'exception'>('active');
  const [progressText, setProgressText] = useState('');
  const [stage, setStage] = useState('');
  const [clearFirst, setClearFirst] = useState(false);
  const [forceReingest, setForceReingest] = useState(false);
  const [ingestionFiles, setIngestionFiles] = useState<IngestionFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  // 原始文件管理状态
  const [rawFiles, setRawFiles] = useState<RawFile[]>([]);
  const [rawFilesLoading, setRawFilesLoading] = useState(false);
  const [fileSearch, setFileSearch] = useState('');
  const [fileSortField, setFileSortField] = useState<string>('filename');
  const [fileSortOrder, setFileSortOrder] = useState<'ascend' | 'descend'>('ascend');
  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>('');
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => { fetchStats(); fetchIngestionFiles(); fetchRawFiles(); }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      setStats(await res.json());
    } catch {
      message.error('获取统计信息失败');
    }
  };

  const fetchIngestionFiles = async () => {
    setFilesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/ingestion/files`);
      const data = await res.json();
      setIngestionFiles(data.files || []);
    } catch {
      message.error('获取已入库文件列表失败');
    } finally {
      setFilesLoading(false);
    }
  };

  const handleDeleteFile = async (sourceFile: string) => {
    try {
      await fetch(`${API_BASE}/ingestion/files/${encodeURIComponent(sourceFile)}`, { method: 'DELETE' });
      message.success('删除成功');
      fetchIngestionFiles();
      fetchStats();
    } catch {
      message.error('删除失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedFiles.length === 0) return;
    try {
      await fetch(`${API_BASE}/ingestion/files/batch-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: selectedFiles }),
      });
      message.success(`批量删除 ${selectedFiles.length} 个文件成功`);
      setSelectedFiles([]);
      fetchIngestionFiles();
      fetchStats();
    } catch {
      message.error('批量删除失败');
    }
  };

  const handleCleanupDuplicates = async () => {
    try {
      const res = await fetch(`${API_BASE}/ingestion/cleanup-duplicates`, { method: 'POST' });
      const data = await res.json();
      message.success(`清理完成，删除了 ${data.cleaned_count} 个重复记录`);
      fetchIngestionFiles();
    } catch {
      message.error('清理失败');
    }
  };

  // 原始文件管理函数
  const fetchRawFiles = async () => {
    setRawFilesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/files`);
      const data = await res.json();
      setRawFiles(data.files || []);
    } catch {
      message.error('获取原始文件列表失败');
    } finally {
      setRawFilesLoading(false);
    }
  };

  const handleConvertFile = async (filepath: string) => {
    try {
      const res = await fetch(`${API_BASE}/files/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filepath }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        message.success('转换成功');
        fetchRawFiles();
      } else {
        message.error(data.message || '转换失败');
      }
    } catch {
      message.error('转换失败');
    }
  };

  const handleDeleteRawFile = async (filepath: string) => {
    try {
      await fetch(`${API_BASE}/files/${encodeURIComponent(filepath)}`, { method: 'DELETE' });
      message.success('删除成功');
      fetchRawFiles();
    } catch {
      message.error('删除失败');
    }
  };

  const handlePreviewFile = async (filepath: string) => {
    setPreviewLoading(true);
    setPreviewFile(filepath);
    try {
      const res = await fetch(`${API_BASE}/files/${encodeURIComponent(filepath)}/preview`);
      const data = await res.json();
      if (data.status === 'ok') {
        setPreviewContent(data.preview);
      } else {
        message.error(data.message || '预览失败');
        setPreviewFile(null);
      }
    } catch {
      message.error('预览失败');
      setPreviewFile(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // 过滤和排序原始文件
  const filteredAndSortedFiles = useMemo(() => {
    let result = rawFiles;

    // 搜索过滤
    if (fileSearch) {
      result = result.filter(f =>
        f.filename.toLowerCase().includes(fileSearch.toLowerCase())
      );
    }

    // 排序
    result.sort((a, b) => {
      let cmp = 0;
      if (fileSortField === 'filename') {
        cmp = a.filename.localeCompare(b.filename);
      } else if (fileSortField === 'size') {
        cmp = a.size - b.size;
      } else if (fileSortField === 'modified') {
        cmp = a.modified - b.modified;
      }
      return fileSortOrder === 'ascend' ? cmp : -cmp;
    });

    return result;
  }, [rawFiles, fileSearch, fileSortField, fileSortOrder]);

  /** 监听 SSE 进度 */
  const listenProgress = (taskId: string) => {
    console.log('[SSE] 开始监听任务进度:', taskId);
    const es = new EventSource(`${API_BASE}/ingest/progress/${taskId}`);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        console.log('[SSE] 收到完成信号');
        es.close();
        eventSourceRef.current = null;
        return;
      }
      try {
        const data = JSON.parse(e.data);
        console.log('[SSE] 收到进度更新:', data);
        setProgress(data.percent || 0);
        setStage(data.stage || '');
        setProgressText(data.message || '');

        if (data.done) {
          console.log('[SSE] 任务完成:', data);
          if (data.error) {
            setProgressStatus('exception');
            message.error(data.error);
          } else {
            setProgress(100);
            setProgressStatus('success');
            message.success('入库完成');
            fetchStats();
            fetchIngestionFiles(); // 刷新已入库文件列表
          }
          setLoading(false);
          es.close();
          eventSourceRef.current = null;
        }
      } catch (err) {
        console.error('[SSE] 解析数据失败:', err);
      }
    };

    es.onerror = (err) => {
      console.error('[SSE] 连接错误:', err);
      es.close();
      eventSourceRef.current = null;
    };
  };

  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options;
    setLoading(true);
    setProgress(0);
    setProgressStatus('active');
    setStage('上传中');

    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: formData });
      const data = await res.json();

      if (data.status === 'ok') {
        setProgress(100);
        setProgressStatus('success');
        setProgressText('入库完成');
        message.success(`${data.filename} 已入库，${data.result.chunks} 个文本块`);
        onSuccess?.(data);
        fetchStats();
      } else {
        throw new Error(data.message || '上传失败');
      }
    } catch (err: any) {
      setProgressStatus('exception');
      setProgressText('入库失败');
      message.error(err.message || '上传失败');
      onError?.(err);
    } finally {
      setLoading(false);
    }
  };

  const handleIngestAll = async () => {
    setLoading(true);
    setProgress(0);
    setProgressStatus('active');
    setStage('启动中');
    setProgressText('正在启动入库任务...');

    try {
      const res = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clear_first: clearFirst, force_reingest: forceReingest }),
      });
      const data = await res.json();
      if (data.status === 'ok' && data.task_id) {
        listenProgress(data.task_id);
      }
    } catch {
      setProgressStatus('exception');
      setProgressText('启动失败');
      message.error('入库启动失败');
      setLoading(false);
    }
  };

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">数据管理</span>
        <div className="page-header-spacer" />
        <Button icon={<SyncOutlined />} onClick={fetchStats} size="small">
          刷新
        </Button>
      </div>

      {/* 内容 */}
      <div className="page-body">
        {/* 统计 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 24 }}>
          <StatCard
            icon={<DatabaseOutlined />}
            label="向量库条数"
            value={stats?.count?.toLocaleString() ?? '—'}
          />
          <StatCard
            icon={<FileTextOutlined />}
            label="集合名称"
            value={stats?.collection_name ?? '—'}
            small
          />
        </div>

        {/* 上传 */}
        <Section title="上传文件">
          <Upload.Dragger
            name="file"
            customRequest={handleUpload}
            accept=".txt,.md,.pdf,.epub,.docx"
            showUploadList={false}
            disabled={loading}
            style={{
              background: 'var(--bg-base)',
              borderColor: 'var(--border)',
              borderRadius: 'var(--r-md)',
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined style={{ color: 'var(--vermilion)', fontSize: 40 }} />
            </p>
            <p style={{ color: 'var(--ink-80)', fontSize: 14 }}>点击或拖拽文件到此处</p>
            <p style={{ color: 'var(--ink-40)', fontSize: 12 }}>
              支持 .txt .md .pdf .epub .docx
            </p>
          </Upload.Dragger>
        </Section>

        {/* 批量入库 */}
        <Section title="批量入库">
          <p style={{ color: 'var(--ink-60)', fontSize: 13, marginBottom: 14 }}>
            将 backend/data/raw/ 目录下的所有文件执行入库流程
          </p>
          <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
            <Button
              type="primary"
              size="large"
              loading={loading}
              onClick={handleIngestAll}
              icon={<CloudUploadOutlined />}
              style={{ flex: 1 }}
            >
              {loading ? '处理中...' : '执行全部入库'}
            </Button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Checkbox
              checked={clearFirst}
              onChange={(e) => setClearFirst(e.target.checked)}
              disabled={loading}
              style={{ fontSize: 13, color: 'var(--ink-60)' }}
            >
              先清空向量库再入库（避免重复）
            </Checkbox>
            <Checkbox
              checked={forceReingest}
              onChange={(e) => setForceReingest(e.target.checked)}
              disabled={loading}
              style={{ fontSize: 13, color: 'var(--ink-60)' }}
            >
              强制重新入库（忽略去重记录，重新入库所有文件）
            </Checkbox>
          </div>

          {(loading || progress === 100) && (
            <InkProgress
              percent={progress}
              stage={stage}
              message={progressText}
              status={progressStatus}
            />
          )}
        </Section>

        {/* 已入库文件管理 */}
        <Section title="已入库文件管理">
          {/* 统计信息条 */}
          <div className="ingestion-stats-bar">
            <div className="stat-item">
              <FileTextOutlined />
              <span>文件总数：</span>
              <span className="stat-value">{ingestionFiles.length}</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <DatabaseOutlined />
              <span>总 Chunks：</span>
              <span className="stat-value">
                {ingestionFiles.reduce((sum, f) => sum + f.chunk_count, 0).toLocaleString()}
              </span>
            </div>
            {selectedFiles.length > 0 && (
              <>
                <div className="stat-divider" />
                <div className="stat-item">
                  <span>已选择：</span>
                  <span className="stat-value" style={{ color: 'var(--vermilion)' }}>
                    {selectedFiles.length}
                  </span>
                </div>
              </>
            )}
          </div>

          {/* 工具栏 */}
          <div className="ingestion-toolbar">
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchIngestionFiles}
              loading={filesLoading}
              size="small"
            >
              刷新
            </Button>
            <Button
              icon={<ClearOutlined />}
              onClick={handleCleanupDuplicates}
              size="small"
            >
              清理重复
            </Button>
            <div style={{ flex: 1 }} />
            <Popconfirm
              title={`确定要批量删除 ${selectedFiles.length} 个文件的入库记录吗？`}
              description="此操作将同时删除向量库中的对应数据"
              onConfirm={handleBatchDelete}
              okText="确定"
              cancelText="取消"
              disabled={selectedFiles.length === 0}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={selectedFiles.length === 0}
                size="small"
              >
                批量删除 ({selectedFiles.length})
              </Button>
            </Popconfirm>
          </div>

          {/* 文件列表表格 */}
          <div className="ingestion-table">
            <Table
              dataSource={ingestionFiles}
              rowKey="source_file"
              loading={filesLoading}
              size="small"
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 个文件`,
                size: 'small',
              }}
              rowSelection={{
                selectedRowKeys: selectedFiles,
                onChange: (keys) => setSelectedFiles(keys as string[]),
              }}
              columns={[
                {
                  title: '文件名',
                  dataIndex: 'source_file',
                  key: 'source_file',
                  ellipsis: true,
                  render: (text: string) => (
                    <span className="ingestion-filename">
                      <FileTextOutlined />
                      {text}
                    </span>
                  ),
                },
                {
                  title: 'Chunks',
                  dataIndex: 'chunk_count',
                  key: 'chunk_count',
                  width: 100,
                  align: 'center',
                  render: (count: number) => (
                    <span className="ingestion-chunk-tag">{count}</span>
                  ),
                },
                {
                  title: '首次入库',
                  dataIndex: 'first_ingested',
                  key: 'first_ingested',
                  width: 170,
                  render: (text: string) => (
                    <span className="ingestion-time">
                      {new Date(text).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  ),
                },
                {
                  title: '最近入库',
                  dataIndex: 'last_ingested',
                  key: 'last_ingested',
                  width: 170,
                  render: (text: string) => (
                    <span className="ingestion-time">
                      {new Date(text).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  ),
                },
                {
                  title: '操作',
                  key: 'action',
                  width: 60,
                  align: 'center',
                  render: (_, record) => (
                    <Popconfirm
                      title="确定删除此文件的入库记录？"
                      description="将同时删除向量库中的对应数据"
                      onConfirm={() => handleDeleteFile(record.source_file)}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        className="ingestion-action-btn"
                      />
                    </Popconfirm>
                  ),
                },
              ]}
            />
          </div>
        </Section>

        {/* 原始文件管理 */}
        <Section title="原始文件管理">
          {/* 统计信息条 */}
          <div className="ingestion-stats-bar">
            <div className="stat-item">
              <FileTextOutlined />
              <span>文件总数：</span>
              <span className="stat-value">{rawFiles.length}</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span>可入库：</span>
              <span className="stat-value" style={{ color: 'var(--slate-green)' }}>
                {rawFiles.filter(f => f.file_type === '可入库').length}
              </span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span>需转换：</span>
              <span className="stat-value" style={{ color: '#d48806' }}>
                {rawFiles.filter(f => f.file_type === '需转换').length}
              </span>
            </div>
          </div>

          {/* 工具栏 */}
          <div className="ingestion-toolbar">
            <Input.Search
              placeholder="搜索文件名"
              allowClear
              style={{ width: 200 }}
              onSearch={setFileSearch}
              onChange={(e) => setFileSearch(e.target.value)}
            />
            <Select
              placeholder="排序方式"
              style={{ width: 120 }}
              value={fileSortField}
              onChange={setFileSortField}
              options={[
                { value: 'filename', label: '文件名' },
                { value: 'size', label: '大小' },
                { value: 'modified', label: '修改时间' },
              ]}
            />
            <Button
              icon={fileSortOrder === 'ascend' ? '↑' : '↓'}
              onClick={() => setFileSortOrder(fileSortOrder === 'ascend' ? 'descend' : 'ascend')}
              size="small"
            />
            <div style={{ flex: 1 }} />
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchRawFiles}
              loading={rawFilesLoading}
              size="small"
            >
              刷新
            </Button>
          </div>

          {/* 文件列表表格 */}
          <div className="ingestion-table">
            <Table
              dataSource={filteredAndSortedFiles}
              rowKey="filepath"
              loading={rawFilesLoading}
              size="small"
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 个文件`,
                size: 'small',
              }}
              columns={[
                {
                  title: '文件名',
                  dataIndex: 'filename',
                  key: 'filename',
                  ellipsis: true,
                  sorter: true,
                  render: (text: string) => (
                    <span className="ingestion-filename">
                      <FileTextOutlined />
                      {text}
                    </span>
                  ),
                },
                {
                  title: '类型',
                  dataIndex: 'file_type',
                  key: 'file_type',
                  width: 100,
                  render: (type: string) => (
                    <Tag color={type === '可入库' ? 'green' : type === '需转换' ? 'orange' : 'gray'}>
                      {type}
                    </Tag>
                  ),
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  key: 'status',
                  width: 100,
                  render: (status: string) => (
                    <Tag color={
                      status === 'ready' ? 'green' :
                      status === 'converted' ? 'blue' :
                      status === 'pending' ? 'orange' : 'red'
                    }>
                      {status === 'ready' ? '可入库' :
                       status === 'converted' ? '已转换' :
                       status === 'pending' ? '待转换' : '不支持'}
                    </Tag>
                  ),
                },
                {
                  title: '大小',
                  dataIndex: 'size',
                  key: 'size',
                  width: 100,
                  sorter: true,
                  render: (size: number) => formatFileSize(size),
                },
                {
                  title: '操作',
                  key: 'action',
                  width: 200,
                  render: (_, record: RawFile) => (
                    <Space>
                      {record.status === 'pending' && (
                        <Button
                          size="small"
                          icon={<SwapOutlined />}
                          onClick={() => handleConvertFile(record.filepath)}
                        >
                          转换
                        </Button>
                      )}
                      <Button
                        size="small"
                        icon={<SearchOutlined />}
                        onClick={() => handlePreviewFile(record.filepath)}
                      >
                        预览
                      </Button>
                      <Popconfirm
                        title="确定删除此文件？"
                        description="删除后无法恢复"
                        onConfirm={() => handleDeleteRawFile(record.filepath)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                        />
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          </div>
        </Section>

        {/* 文件预览抽屉 */}
        <Drawer
          title={previewFile || '文件预览'}
          placement="right"
          width={500}
          open={!!previewFile}
          onClose={() => {
            setPreviewFile(null);
            setPreviewContent('');
          }}
          loading={previewLoading}
        >
          <pre style={{
            whiteSpace: 'pre-wrap',
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            lineHeight: 1.8,
            color: 'var(--ink-80)',
            background: 'var(--bg-base)',
            padding: 16,
            borderRadius: 'var(--r-md)',
            maxHeight: 'calc(100vh - 200px)',
            overflow: 'auto',
          }}>
            {previewContent}
          </pre>
        </Drawer>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, small }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  small?: boolean;
}) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--r-md)',
      padding: '16px 18px',
    }}>
      <div style={{ fontSize: 12, color: 'var(--ink-40)', marginBottom: 4 }}>
        {icon} {label}
      </div>
      <div style={{
        fontSize: small ? 18 : 26,
        fontWeight: 700,
        fontFamily: 'var(--font-display)',
        color: 'var(--ink-100)',
      }}>
        {value}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
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
        {title}
      </h3>
      {children}
    </div>
  );
}
