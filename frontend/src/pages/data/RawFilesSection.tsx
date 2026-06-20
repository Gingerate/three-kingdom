import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Button, Table, Popconfirm, Input, Select, Space, Tag, Drawer, message } from 'antd';
import {
  FileTextOutlined,
  ReloadOutlined,
  DeleteOutlined,
  SwapOutlined,
  SearchOutlined,
  CloudUploadOutlined,
  FilterOutlined,
} from '@ant-design/icons';
import {
  getRawFiles,
  convertFile,
  deleteRawFile,
  previewFile as previewFileApi,
  ingestData,
  API_BASE,
} from '../../services/api';
import Section from './Section';

interface RawFile {
  filename: string;
  filepath: string;
  size: number;
  modified: number;
  status: string;
  suffix: string;
}

// 状态配置（4 种：待转换 / 可入库 / 已入库 / 不支持）
const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  pending: { label: '待转换', color: 'orange' },
  ready: { label: '可入库', color: 'green' },
  ingested: { label: '已入库', color: 'purple' },
  unsupported: { label: '不支持', color: 'default' },
};

interface RawFilesSectionProps {
  onRefresh?: () => void;
}

/** 原始文件管理区域 */
export default function RawFilesSection({ onRefresh }: RawFilesSectionProps) {
  const [files, setFiles] = useState<RawFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [fileSearch, setFileSearch] = useState('');
  const [fileStatusFilter, setFileStatusFilter] = useState<string>('');
  const [fileSortField, setFileSortField] = useState<string>('filename');
  const [fileSortOrder, setFileSortOrder] = useState<'ascend' | 'descend'>('ascend');
  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [batchConverting, setBatchConverting] = useState(false);
  const [batchIngesting, setBatchIngesting] = useState(false);
  const evtSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetchFiles();
    // 组件卸载时关闭所有 SSE 连接
    return () => {
      if (evtSourceRef.current) {
        evtSourceRef.current.close();
        evtSourceRef.current = null;
      }
    };
  }, []);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await getRawFiles();
      setFiles(data.files || []);
    } catch {
      message.error('获取原始文件列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleConvertFile = async (filepath: string) => {
    try {
      const data = await convertFile(filepath);
      if (data.status === 'ok') {
        message.success('转换成功');
        fetchFiles();
      } else {
        message.error(data.message || '转换失败');
      }
    } catch {
      message.error('转换失败');
    }
  };

  // 单文件入库（带 SSE 进度监听）
  const handleIngestFile = useCallback((filepath: string) => {
    const taskMessage = message.loading('入库任务提交中...', 0);

    ingestData({ files: [filepath] })
      .then((data) => {
        taskMessage();
        if (data.status !== 'ok') {
          message.error(data.message || '入库失败');
          return;
        }

        // 监听 SSE 进度
        const taskId = data.task_id;
        const evtSource = new EventSource(`${API_BASE}/ingest/progress/${taskId}`);
        evtSourceRef.current = evtSource;

        evtSource.onmessage = (event) => {
          if (event.data === '[DONE]') {
            evtSource.close();
            evtSourceRef.current = null;
            return;
          }
          try {
            const progress = JSON.parse(event.data);
            if (progress.done) {
              evtSource.close();
              evtSourceRef.current = null;
              if (progress.error) {
                message.error(`入库失败：${progress.error}`);
              } else {
                message.success('入库完成');
                fetchFiles();
                onRefresh?.();
              }
            }
          } catch {
            // 忽略解析错误
          }
        };

        evtSource.onerror = () => {
          evtSource.close();
          evtSourceRef.current = null;
          message.error('入库进度连接断开');
        };
      })
      .catch(() => {
        taskMessage();
        message.error('入库任务提交失败');
      });
  }, [onRefresh]);

  const handleDeleteRawFile = async (filepath: string) => {
    try {
      await deleteRawFile(filepath);
      message.success('删除成功');
      fetchFiles();
    } catch {
      message.error('删除失败');
    }
  };

  const handlePreviewFile = async (filepath: string) => {
    setPreviewLoading(true);
    setPreviewFile(filepath);
    try {
      const data = await previewFileApi(filepath);
      if (data.preview) {
        setPreviewContent(data.preview);
      } else {
        message.error('预览失败');
        setPreviewFile(null);
      }
    } catch {
      message.error('预览失败');
      setPreviewFile(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // 批量转换（前端并发调用，最多 3 个并发）
  const handleBatchConvert = async () => {
    const pendingFiles = files.filter(f => selectedKeys.includes(f.filepath) && f.status === 'pending');
    if (pendingFiles.length === 0) {
      message.warning('选中的文件中没有待转换的文件');
      return;
    }

    setBatchConverting(true);
    let success = 0;
    let fail = 0;
    const concurrency = 3;

    for (let i = 0; i < pendingFiles.length; i += concurrency) {
      const batch = pendingFiles.slice(i, i + concurrency);
      const results = await Promise.allSettled(
        batch.map(f => convertFile(f.filepath))
      );
      results.forEach(r => {
        if (r.status === 'fulfilled' && r.value?.status === 'ok') {
          success++;
        } else {
          fail++;
        }
      });
      message.loading({ content: `转换进度 ${Math.min(i + concurrency, pendingFiles.length)}/${pendingFiles.length}`, key: 'batchConvert' });
    }

    message.destroy('batchConvert');
    if (fail === 0) {
      message.success(`批量转换完成：${success} 个文件全部成功`);
    } else {
      message.warning(`批量转换完成：成功 ${success}，失败 ${fail}`);
    }
    setSelectedKeys([]);
    fetchFiles();
    setBatchConverting(false);
  };

  // 批量入库（带 SSE 进度监听）
  const handleBatchIngest = async () => {
    const ingestibleFiles = files.filter(
      f => selectedKeys.includes(f.filepath) && f.status === 'ready'
    );
    if (ingestibleFiles.length === 0) {
      message.warning('选中的文件中没有可入库的文件');
      return;
    }

    setBatchIngesting(true);
    const taskMessage = message.loading('入库任务提交中...', 0);

    try {
      const data = await ingestData({ files: ingestibleFiles.map(f => f.filepath) });
      taskMessage();

      if (data.status !== 'ok') {
        message.error(data.message || '入库失败');
        setBatchIngesting(false);
        return;
      }

      // 监听 SSE 进度
      const taskId = data.task_id;
      const evtSource = new EventSource(`${API_BASE}/ingest/progress/${taskId}`);
      evtSourceRef.current = evtSource;

      evtSource.onmessage = (event) => {
        if (event.data === '[DONE]') {
          evtSource.close();
          evtSourceRef.current = null;
          setSelectedKeys([]);
          setBatchIngesting(false);
          return;
        }
        try {
          const progress = JSON.parse(event.data);
          if (progress.done) {
            evtSource.close();
            evtSourceRef.current = null;
            setSelectedKeys([]);
            setBatchIngesting(false);
            if (progress.error) {
              message.error(`入库失败：${progress.error}`);
            } else {
              message.success(`批量入库完成，共 ${ingestibleFiles.length} 个文件`);
              fetchFiles();
              onRefresh?.();
            }
          }
        } catch {
          // 忽略解析错误
        }
      };

      evtSource.onerror = () => {
        evtSource.close();
        evtSourceRef.current = null;
        setSelectedKeys([]);
        setBatchIngesting(false);
        message.error('入库进度连接断开');
      };
    } catch {
      taskMessage();
      setSelectedKeys([]);
      setBatchIngesting(false);
      message.error('入库任务提交失败');
    }
  };

  // 快捷选择：全选符合指定状态的文件（跨页生效）
  const handleQuickSelect = (status: string) => {
    const keys = files.filter(f => f.status === status).map(f => f.filepath);
    setSelectedKeys(keys);
  };

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // 过滤和排序原始文件
  const filteredAndSortedFiles = useMemo(() => {
    let result = [...files];

    if (fileSearch) {
      result = result.filter(f =>
        f.filename.toLowerCase().includes(fileSearch.toLowerCase())
      );
    }

    if (fileStatusFilter) {
      result = result.filter(f => f.status === fileStatusFilter);
    }

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
  }, [files, fileSearch, fileStatusFilter, fileSortField, fileSortOrder]);

  // 选中文件的状态统计
  const selectedStats = useMemo(() => {
    const selected = files.filter(f => selectedKeys.includes(f.filepath));
    return {
      pending: selected.filter(f => f.status === 'pending').length,
      ingestible: selected.filter(f => f.status === 'ready').length,
    };
  }, [files, selectedKeys]);

  return (
    <Section title="原始文件管理">
      {/* 统计信息条 */}
      <div className="ingestion-stats-bar">
        <div className="stat-item">
          <FileTextOutlined />
          <span>文件总数：</span>
          <span className="stat-value">{files.length}</span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item">
          <span>待转换：</span>
          <span className="stat-value" style={{ color: '#d48806' }}>
            {files.filter(f => f.status === 'pending').length}
          </span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item">
          <span>可入库：</span>
          <span className="stat-value" style={{ color: 'var(--slate-green)' }}>
            {files.filter(f => f.status === 'ready').length}
          </span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item">
          <span>已入库：</span>
          <span className="stat-value" style={{ color: '#722ed1' }}>
            {files.filter(f => f.status === 'ingested').length}
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
          placeholder="状态筛选"
          allowClear
          style={{ width: 120 }}
          value={fileStatusFilter || undefined}
          onChange={(v) => setFileStatusFilter(v || '')}
          options={[
            { value: 'pending', label: '待转换' },
            { value: 'ready', label: '可入库' },
            { value: 'ingested', label: '已入库' },
            { value: 'unsupported', label: '不支持' },
          ]}
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

        {/* 快捷选择按钮（未选中时显示） */}
        {selectedKeys.length === 0 && (
          <Space size={4}>
            <Button
              size="small"
              icon={<FilterOutlined />}
              onClick={() => handleQuickSelect('pending')}
            >
              全选待转换
            </Button>
            <Button
              size="small"
              icon={<FilterOutlined />}
              onClick={() => handleQuickSelect('ready')}
            >
              全选可入库
            </Button>
          </Space>
        )}

        {/* 批量操作按钮（选中后显示） */}
        {selectedKeys.length > 0 && (
          <Space size={4}>
            <span style={{ fontSize: 12, color: 'var(--color-ink-4)' }}>
              已选 {selectedKeys.length} 个
            </span>
            {selectedStats.pending > 0 && (
              <Button
                size="small"
                type="primary"
                icon={<SwapOutlined />}
                loading={batchConverting}
                onClick={handleBatchConvert}
              >
                批量转换 ({selectedStats.pending})
              </Button>
            )}
            {selectedStats.ingestible > 0 && (
              <Button
                size="small"
                type="primary"
                icon={<CloudUploadOutlined />}
                loading={batchIngesting}
                onClick={handleBatchIngest}
              >
                批量入库 ({selectedStats.ingestible})
              </Button>
            )}
            <Button
              size="small"
              onClick={() => setSelectedKeys([])}
            >
              取消选择
            </Button>
          </Space>
        )}

        <Button
          icon={<ReloadOutlined />}
          onClick={fetchFiles}
          loading={loading}
          size="small"
        >
          刷新
        </Button>
      </div>

      {/* 文件列表表格 */}
      <div className="themed-table">
        <Table
          dataSource={filteredAndSortedFiles}
          rowKey="filepath"
          loading={loading}
          size="small"
          rowSelection={{
            selectedRowKeys: selectedKeys,
            onChange: (keys) => setSelectedKeys(keys as string[]),
          }}
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
              width: 300,
              sorter: true,
              render: (text: string) => (
                <span className="ingestion-filename">
                  <FileTextOutlined />
                  {text}
                </span>
              ),
            },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              width: 100,
              render: (status: string) => {
                const config = STATUS_CONFIG[status] || { label: status, color: 'default' };
                return <Tag color={config.color}>{config.label}</Tag>;
              },
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
                  {record.status === 'ready' && (
                    <Button
                      size="small"
                      type="primary"
                      icon={<CloudUploadOutlined />}
                      onClick={() => handleIngestFile(record.filepath)}
                    >
                      入库
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
          color: 'var(--color-ink-2)',
          background: 'var(--color-paper)',
          padding: 16,
          borderRadius: 'var(--radius-md)',
          maxHeight: 'calc(100vh - 200px)',
          overflow: 'auto',
        }}>
          {previewContent}
        </pre>
      </Drawer>
    </Section>
  );
}
