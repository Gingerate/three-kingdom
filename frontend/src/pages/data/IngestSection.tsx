import { useState, useRef, useEffect } from 'react';
import { Button, Checkbox, message } from 'antd';
import { CloudUploadOutlined } from '@ant-design/icons';
import InkProgress from '../../components/InkProgress';
import { API_BASE, ingestData } from '../../services/api';
import Section from './Section';

interface IngestSectionProps {
  onSuccess?: () => void;
}

/** 批量入库区域 */
export default function IngestSection({ onSuccess }: IngestSectionProps) {
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState<'active' | 'success' | 'exception'>('active');
  const [progressText, setProgressText] = useState('');
  const [stage, setStage] = useState('');
  const [clearFirst, setClearFirst] = useState(false);
  const [forceReingest, setForceReingest] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  // 组件卸载时清理 SSE 连接
  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, []);

  /** 监听 SSE 进度 */
  const listenProgress = (taskId: string) => {
    console.log('[SSE] 开始监听任务进度:', taskId);
    if (esRef.current) {
      esRef.current.close();
    }
    const es = new EventSource(`${API_BASE}/ingest/progress/${taskId}`);
    esRef.current = es;

    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        console.log('[SSE] 收到完成信号');
        es.close();
        esRef.current = null;
        return;
      }
      try {
        const data = JSON.parse(e.data);
        console.log('[SSE] 收到进度更新:', data);
        setProgress(data.percent || 0);
        setStage(data.stage || '');
        setProgressText(data.message || '');

        if (data.done) {
          console.log('[SSE] 任务完成:', data);
          if (data.error) {
            setProgressStatus('exception');
            message.error(data.error);
          } else {
            setProgress(100);
            setProgressStatus('success');
            message.success('入库完成');
            onSuccess?.();
          }
          setLoading(false);
          es.close();
          esRef.current = null;
        }
      } catch (err) {
        console.error('[SSE] 解析数据失败:', err);
      }
    };

    es.onerror = (err) => {
      console.error('[SSE] 连接错误:', err);
      es.close();
      esRef.current = null;
      setLoading(false);
      setProgressStatus('exception');
      setProgressText('连接中断，请重试');
      message.error('进度连接中断');
    };
  };

  const handleIngestAll = async () => {
    setLoading(true);
    setProgress(0);
    setProgressStatus('active');
    setStage('启动中');
    setProgressText('正在启动入库任务...');

    try {
      const data = await ingestData({ clear_first: clearFirst, force_reingest: forceReingest });
      if (data.status === 'ok' && data.task_id) {
        listenProgress(data.task_id);
      } else {
        setProgressStatus('exception');
        setProgressText(data.message || '启动失败');
        message.error(data.message || '入库启动失败');
        setLoading(false);
      }
    } catch {
      setProgressStatus('exception');
      setProgressText('启动失败');
      message.error('入库启动失败');
      setLoading(false);
    }
  };

  return (
    <Section title="批量入库">
      <p style={{ color: 'var(--color-ink-3)', fontSize: 13, marginBottom: 14 }}>
        将 backend/data/raw/ 目录下的所有文件执行入库流程
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
        <Button
          type="primary"
          size="large"
          loading={loading}
          onClick={handleIngestAll}
          icon={<CloudUploadOutlined />}
          style={{ flex: 1 }}
        >
          {loading ? '处理中...' : '执行全部入库'}
        </Button>
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

      {(loading || progress === 100) && (
        <InkProgress
          percent={progress}
          stage={stage}
          message={progressText}
          status={progressStatus}
        />
      )}
    </Section>
  );
}
