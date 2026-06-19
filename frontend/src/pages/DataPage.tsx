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
        <StatsSection count={stats?.count} collectionName={stats?.collection_name} />

        {/* 输入区：上传 + 入库 + 抽取 */}
        <div className="data-section-group">
          <UploadSection onSuccess={fetchStats} />
          <IngestSection onSuccess={fetchStats} />
          <ExtractSection />
        </div>

        {/* 管理区：已入库 + 原始文件 */}
        <div className="data-section-group">
          <IngestionFilesSection onRefresh={fetchStats} />
          <RawFilesSection />
        </div>
      </div>
    </div>
  );
}
