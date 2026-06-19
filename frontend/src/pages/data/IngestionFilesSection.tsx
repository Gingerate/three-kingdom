import { useState, useEffect } from 'react';
import { Button, Table, Popconfirm, message, Tag } from 'antd';
import { FileTextOutlined, DatabaseOutlined, ReloadOutlined, ClearOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  getIngestionFiles,
  deleteIngestionFile,
  batchDeleteIngestionFiles,
  cleanupDuplicates,
} from '../../services/api';
import Section from './Section';

interface IngestionFile {
  source_file: string;
  source_name: string;
  chunk_count: number;
  first_ingested: string;
  last_ingested: string;
}

interface IngestionFilesSectionProps {
  onRefresh?: () => void;
}

/** 已入库文件管理区域 */
export default function IngestionFilesSection({ onRefresh }: IngestionFilesSectionProps) {
  const [files, setFiles] = useState<IngestionFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);

  useEffect(() => {
    fetchFiles();
  }, []);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await getIngestionFiles();
      setFiles(data.files || []);
    } catch {
      message.error('获取已入库文件列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteFile = async (sourceFile: string) => {
    try {
      await deleteIngestionFile(sourceFile);
      message.success('删除成功');
      fetchFiles();
      onRefresh?.();
    } catch {
      message.error('删除失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedFiles.length === 0) return;
    try {
      await batchDeleteIngestionFiles(selectedFiles);
      message.success(`批量删除 ${selectedFiles.length} 个文件成功`);
      setSelectedFiles([]);
      fetchFiles();
      onRefresh?.();
    } catch {
      message.error('批量删除失败');
    }
  };

  const handleCleanupDuplicates = async () => {
    try {
      const data = await cleanupDuplicates();
      message.success(`清理完成，删除了 ${data.cleaned_count} 个重复记录`);
      fetchFiles();
    } catch {
      message.error('清理失败');
    }
  };

  return (
    <Section title="已入库文件管理">
      {/* 统计信息条 */}
      <div className="ingestion-stats-bar">
        <div className="stat-item">
          <FileTextOutlined />
          <span>文件总数：</span>
          <span className="stat-value">{files.length}</span>
        </div>
        <div className="stat-divider" />
        <div className="stat-item">
          <DatabaseOutlined />
          <span>总 Chunks：</span>
          <span className="stat-value">
            {files.reduce((sum, f) => sum + f.chunk_count, 0).toLocaleString()}
          </span>
        </div>
        {selectedFiles.length > 0 && (
          <>
            <div className="stat-divider" />
            <div className="stat-item">
              <span>已选择：</span>
              <span className="stat-value" style={{ color: 'var(--color-accent)' }}>
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
          onClick={fetchFiles}
          loading={loading}
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
      <div className="themed-table">
        <Table
          dataSource={files}
          rowKey="source_file"
          loading={loading}
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
              title: '文件路径',
              dataIndex: 'source_file',
              key: 'source_file',
              ellipsis: true,
              render: (text: string, record: any) => (
                <span className="ingestion-filename">
                  <FileTextOutlined />
                  {text}
                  {record.source_name && record.source_name !== text && (
                    <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>
                      {record.source_name}
                    </Tag>
                  )}
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
  );
}
