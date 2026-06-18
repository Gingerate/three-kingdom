import { useState, useEffect, useMemo } from 'react';
import { Button, Table, Popconfirm, Input, Select, Space, Tag, Drawer, message } from 'antd';
import { FileTextOutlined, ReloadOutlined, DeleteOutlined, SwapOutlined, SearchOutlined } from '@ant-design/icons';
import {
  getRawFiles,
  convertFile,
  deleteRawFile,
  previewFile as previewFileApi,
} from '../../services/api';
import Section from './Section';

interface RawFile {
  filename: string;
  filepath: string;
  size: number;
  modified: number;
  file_type: string;
  status: string;
  suffix: string;
}

/** 原始文件管理区域 */
export default function RawFilesSection() {
  const [files, setFiles] = useState<RawFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [fileSearch, setFileSearch] = useState('');
  const [fileStatusFilter, setFileStatusFilter] = useState<string>('');
  const [fileSortField, setFileSortField] = useState<string>('filename');
  const [fileSortOrder, setFileSortOrder] = useState<'ascend' | 'descend'>('ascend');
  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>('');
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    fetchFiles();
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

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // 过滤和排序原始文件
  const filteredAndSortedFiles = useMemo(() => {
    let result = [...files];

    // 搜索过滤
    if (fileSearch) {
      result = result.filter(f =>
        f.filename.toLowerCase().includes(fileSearch.toLowerCase())
      );
    }

    // 状态过滤
    if (fileStatusFilter) {
      result = result.filter(f => f.status === fileStatusFilter);
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
  }, [files, fileSearch, fileStatusFilter, fileSortField, fileSortOrder]);

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
          <span>可入库：</span>
          <span className="stat-value" style={{ color: 'var(--slate-green)' }}>
            {files.filter(f => f.file_type === '可入库').length}
          </span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item">
          <span>需转换：</span>
          <span className="stat-value" style={{ color: '#d48806' }}>
            {files.filter(f => f.file_type === '需转换').length}
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
            { value: 'ready', label: '可入库' },
            { value: 'converted', label: '已转换' },
            { value: 'pending', label: '待转换' },
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
              width: 260,
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
    </Section>
  );
}
