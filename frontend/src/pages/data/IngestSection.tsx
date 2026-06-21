import { useState } from 'react';
import { Button, Checkbox, message } from 'antd';
import { CloudUploadOutlined, StopOutlined } from '@ant-design/icons';
import InkProgress from '../../components/InkProgress';
import { ingestData } from '../../services/api';
import { useTask } from '../../contexts/TaskContext';
import Section from './Section';

interface IngestSectionProps {
  onSuccess?: () => void;
}

/** 批量入库区域 */
export default function IngestSection({ onSuccess }: IngestSectionProps) {
  const { getTask, startListening, cancel, setTaskLoading, resetTask } = useTask();
  const task = getTask('ingest');
  const loading = task?.loading ?? false;
  const [starting, setStarting] = useState(false);
  const [clearFirst, setClearFirst] = useState(false);
  const [forceReingest, setForceReingest] = useState(false);

  const handleIngestAll = async () => {
    setStarting(true);
    setTaskLoading('ingest', true);

    try {
      const data = await ingestData({ clear_first: clearFirst, force_reingest: forceReingest });
      if (data.status === 'ok' && data.task_id) {
        startListening('ingest', data.task_id, { onComplete: onSuccess });
      } else {
        resetTask('ingest');
        message.error(data.message || '入库启动失败');
      }
    } catch {
      resetTask('ingest');
      message.error('入库启动失败');
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    await cancel('ingest');
  };

  // 决定进度条显示状态
  const showProgress = task && (task.loading || task.status === 'success' || task.status === 'exception' || task.status === 'cancelled');
  const progressPercent = task?.progress ?? 0;
  const progressStatus = task?.status === 'exception' ? 'exception'
    : task?.status === 'cancelled' ? 'exception'
    : task?.status === 'success' ? 'success'
    : 'active';

  return (
    <Section title="批量入库">
      <p style={{ color: 'var(--color-ink-3)', fontSize: 13, marginBottom: 14 }}>
        将 backend/data/raw/ 目录下的所有文件执行入库流程
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
        <Button
          type="primary"
          size="large"
          loading={starting}
          onClick={handleIngestAll}
          icon={<CloudUploadOutlined />}
          style={{ flex: 1 }}
          disabled={loading}
        >
          {loading ? '处理中...' : '执行全部入库'}
        </Button>
        {loading && (
          <Button
            size="large"
            danger
            onClick={handleCancel}
            icon={<StopOutlined />}
          >
            取消
          </Button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Checkbox
          checked={clearFirst}
          onChange={(e) => setClearFirst(e.target.checked)}
          disabled={loading}
          style={{ fontSize: 13, color: 'var(--color-ink-3)' }}
        >
          先清空向量库再入库（避免重复）
        </Checkbox>
        <Checkbox
          checked={forceReingest}
          onChange={(e) => setForceReingest(e.target.checked)}
          disabled={loading}
          style={{ fontSize: 13, color: 'var(--color-ink-3)' }}
        >
          强制重新入库（忽略去重记录，重新入库所有文件）
        </Checkbox>
      </div>

      {showProgress && (
        <InkProgress
          percent={progressPercent}
          stage={task?.stage || ''}
          message={task?.status === 'cancelled' ? '已取消' : task?.message || ''}
          status={progressStatus}
        />
      )}
    </Section>
  );
}
