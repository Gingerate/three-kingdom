import { useState, useEffect } from 'react';
import { Button, Tag, Spin, message, Table, Popconfirm, Modal, Descriptions, Space, Input } from 'antd';
import { CheckOutlined, CloseOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import { getPendingReviews, getReviewDetail, approveReview, rejectReview } from '../services/api';
import EmptyState from '../components/EmptyState';

interface ReviewItem {
  id: number;
  source_text: string;
  entities: any[];
  relations: any[];
  status: string;
  reason: string;
  created_at: string;
}

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedItem, setSelectedItem] = useState<ReviewItem | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    setLoading(true);
    try {
      const data = await getPendingReviews();
      setItems(data.items || []);
    } catch {
      message.error('加载审核列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (reviewId: number) => {
    setDetailLoading(true);
    setDetailModalVisible(true);
    try {
      const detail = await getReviewDetail(reviewId);
      setSelectedItem(detail);
    } catch {
      message.error('获取详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleApprove = async (reviewId: number) => {
    try {
      await approveReview(reviewId);
      message.success('审核通过');
      loadItems();
    } catch {
      message.error('审核失败');
    }
  };

  const handleReject = async (reviewId: number) => {
    const reasonRef = { current: '' };
    Modal.confirm({
      title: '拒绝审核项',
      content: (
        <div>
          <p>请输入拒绝原因（可选）：</p>
          <Input.TextArea
            rows={3}
            onChange={(e) => { reasonRef.current = e.target.value; }}
            placeholder="拒绝原因..."
          />
        </div>
      ),
      okText: '确认拒绝',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await rejectReview(reviewId, reasonRef.current);
          message.success('已拒绝');
          loadItems();
        } catch {
          message.error('拒绝失败');
        }
      },
    });
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '来源文本',
      dataIndex: 'source_text',
      key: 'source_text',
      ellipsis: true,
      render: (text: string) => (
        <span style={{ fontSize: 13 }}>{text.slice(0, 100)}...</span>
      ),
    },
    {
      title: '实体数',
      key: 'entity_count',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: ReviewItem) => (
        <Tag color="blue">{record.entities.length}</Tag>
      ),
    },
    {
      title: '关系数',
      key: 'relation_count',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: ReviewItem) => (
        <Tag color="green">{record.relations.length}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: ReviewItem) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record.id)}
          >
            查看
          </Button>
          <Popconfirm
            title="确定审核通过？"
            description="将把实体和关系写入知识图谱"
            onConfirm={() => handleApprove(record.id)}
          >
            <Button size="small" type="primary" icon={<CheckOutlined />}>
              通过
            </Button>
          </Popconfirm>
          <Popconfirm
            title="确定拒绝？"
            onConfirm={() => handleReject(record.id)}
          >
            <Button size="small" danger icon={<CloseOutlined />}>
              拒绝
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">审核队列</span>
        <Tag style={{ fontSize: 11 }}>{items.length} 条待审核</Tag>
        <div className="page-header-spacer" />
        <Button icon={<ReloadOutlined />} onClick={loadItems} loading={loading} size="small">
          刷新
        </Button>
      </div>

      {/* 内容 */}
      <div className="page-body">
        {items.length === 0 && !loading ? (
          <EmptyState
            icon={<CheckOutlined />}
            title="暂无待审核项"
            description="知识抽取后会自动进入审核队列"
          />
        ) : (
          <div className="themed-table">
            <Table
              dataSource={items}
              columns={columns}
              rowKey="id"
              loading={loading}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          </div>
        )}
      </div>

      {/* 详情 Modal */}
      <Modal
        title={`审核项详情 #${selectedItem?.id || ''}`}
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={null}
        width={700}
        className="themed-modal"
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : selectedItem ? (
          <div>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="来源文本">
                <div style={{ maxHeight: 150, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                  {selectedItem.source_text}
                </div>
              </Descriptions.Item>
            </Descriptions>

            <h4 style={{ marginBottom: 8 }}>抽取的实体 ({selectedItem.entities.length})</h4>
            <Table
              dataSource={selectedItem.entities}
              rowKey={(_, i) => String(i)}
              size="small"
              pagination={false}
              style={{ marginBottom: 16 }}
              columns={[
                { title: '名称', dataIndex: 'name', key: 'name' },
                { title: '类型', dataIndex: 'entity_type', key: 'entity_type',
                  render: (t: string) => <Tag>{t}</Tag> },
                { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
              ]}
            />

            <h4 style={{ marginBottom: 8 }}>抽取的关系 ({selectedItem.relations.length})</h4>
            <Table
              dataSource={selectedItem.relations}
              rowKey={(_, i) => String(i)}
              size="small"
              pagination={false}
              columns={[
                { title: '源', dataIndex: 'source_name', key: 'source_name' },
                { title: '关系', dataIndex: 'relation_type', key: 'relation_type' },
                { title: '目标', dataIndex: 'target_name', key: 'target_name' },
                { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
              ]}
            />
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
