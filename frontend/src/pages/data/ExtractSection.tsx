import { useState } from 'react';
import { Button, message } from 'antd';
import { BranchesOutlined, StopOutlined } from '@ant-design/icons';
import InkProgress from '../../components/InkProgress';
import { extractBatch } from '../../services/api';
import { useTask } from '../../contexts/TaskContext';
import Section from './Section';

/** 批量知识抽取区域 */
export default function ExtractSection() {
  const { getTask, startListening, cancel, setTaskLoading, resetTask } = useTask();
  const task = getTask('extract');
  const loading = task?.loading ?? false;
  const [starting, setStarting] = useState(false);

  const handleExtractBatch = async () => {
    setStarting(true);
    setTaskLoading('extract', true);

    try {
      const data = await extractBatch();
      if (data.status === 'ok' && data.task_id) {
        startListening('extract', data.task_id);
      } else {
        resetTask('extract');
        message.error(data.message || '批量抽取启动失败');
      }
    } catch {
      resetTask('extract');
      message.error('批量抽取启动失败');
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    await cancel('extract');
  };

  // 决定进度条显示状态
  const showProgress = task && (task.loading || task.status === 'success' || task.status === 'exception' || task.status === 'cancelled');
  const progressPercent = task?.progress ?? 0;
  const progressStatus = task?.status === 'exception' ? 'exception'
    : task?.status === 'cancelled' ? 'exception'
    : task?.status === 'success' ? 'success'
    : 'active';

  return (
    <Section title="批量知识抽取">
      <p style={{ color: 'var(--color-ink-3)', fontSize: 13, marginBottom: 14 }}>
        对 raw/ 目录下的所有语料进行知识抽取，结果进入审核队列
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
        <Button
          type="primary"
          size="large"
          loading={starting}
          onClick={handleExtractBatch}
          icon={<BranchesOutlined />}
          style={{ flex: 1 }}
          disabled={loading}
        >
          {loading ? '抽取中...' : '执行批量抽取'}
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
