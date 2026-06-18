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

        {/* 上传 */}
        <UploadSection
          loading={false}
          setLoading={() => {}}
          setProgress={() => {}}
          setProgressStatus={() => {}}
          setStage={() => {}}
          setProgressText={() => {}}
          onSuccess={fetchStats}
        />

        {/* 批量入库 */}
        <IngestSection onSuccess={fetchStats} />

        {/* 批量知识抽取 */}
        <ExtractSection />

        {/* 已入库文件管理 */}
        <IngestionFilesSection onRefresh={fetchStats} />

        {/* 原始文件管理 */}
        <RawFilesSection />
      </div>
    </div>
  );
}
