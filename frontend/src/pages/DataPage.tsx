import { useState, useEffect } from 'react';
import { Button, message } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import { getStats } from '../services/api';
import {
  StatsSection,
  UploadSection,
  IngestSection,
  ExtractSection,
  IngestionFilesSection,
  RawFilesSection,
} from './data';

export default function DataPage() {
  const [stats, setStats] = useState<{ count: number; collection_name: string } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const data = await getStats();
      setStats(data);
    } catch {
      message.error('获取统计信息失败');
    }
  };

  /** 刷新统计 + 触发子组件重新加载 */
  const handleRefresh = () => {
    fetchStats();
    setRefreshKey(k => k + 1);
  };

  return (
    <div className="page-shell">
      {/* 顶栏 */}
      <div className="page-header">
        <span className="page-header-title">数据管理</span>
        <div className="page-header-spacer" />
        <Button icon={<SyncOutlined />} onClick={handleRefresh} size="small">
          刷新
        </Button>
      </div>

      {/* 内容 */}
      <div className="page-body">
        {/* 统计 */}
        <StatsSection count={stats?.count} collectionName={stats?.collection_name} />

        {/* 输入区：上传 + 入库 + 抽取 */}
        <div className="data-section-group">
          <UploadSection onSuccess={handleRefresh} />
          <IngestSection onSuccess={handleRefresh} />
          <ExtractSection />
        </div>

        {/* 管理区：已入库 + 原始文件 */}
        <div className="data-section-group">
          <IngestionFilesSection onRefresh={handleRefresh} refreshKey={refreshKey} />
          <RawFilesSection onRefresh={handleRefresh} />
        </div>
      </div>
    </div>
  );
}
