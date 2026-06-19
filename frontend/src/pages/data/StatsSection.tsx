import { DatabaseOutlined, FileTextOutlined } from '@ant-design/icons';

interface StatsSectionProps {
  count: number | undefined;
  collectionName: string | undefined;
}

/** 统计卡片组件 */
function StatCard({ icon, label, value, small }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  small?: boolean;
}) {
  return (
    <div className="stat-card">
      <div style={{ fontSize: 12, color: 'var(--color-ink-4)', marginBottom: 4 }}>
        {icon} {label}
      </div>
      <div style={{
        fontSize: small ? 18 : 26,
        fontWeight: 700,
        fontFamily: 'var(--font-display)',
        color: 'var(--color-ink)',
      }}>
        {value}
      </div>
    </div>
  );
}

/** 统计信息区域 */
export default function StatsSection({ count, collectionName }: StatsSectionProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 24 }}>
      <StatCard
        icon={<DatabaseOutlined />}
        label="向量库条数"
        value={count?.toLocaleString() ?? '—'}
      />
      <StatCard
        icon={<FileTextOutlined />}
        label="集合名称"
        value={collectionName ?? '—'}
        small
      />
    </div>
  );
}
