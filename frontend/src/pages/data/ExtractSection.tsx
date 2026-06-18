import { useState, useRef, useEffect } from 'react';
import { Button, message } from 'antd';
import { BranchesOutlined } from '@ant-design/icons';
import InkProgress from '../../components/InkProgress';
import { API_BASE, extractBatch } from '../../services/api';
import Section from './Section';

/** 批量知识抽取区域 */
export default function ExtractSection() {
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState<'active' | 'success' | 'exception'>('active');
  const [progressText, setProgressText] = useState('');
  const [stage, setStage] = useState('');
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

  /** 监听批量抽取 SSE 进度 */
  const listenExtractProgress = (taskId: string) => {
    console.log('[SSE] 开始监听批量抽取进度:', taskId);
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
            message.success('批量抽取完成，结果已加入审核队列');
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

  const handleExtractBatch = async () => {
    setLoading(true);
    setProgress(0);
    setProgressStatus('active');
    setStage('启动中');
    setProgressText('正在启动批量抽取任务...');

    try {
      const data = await extractBatch();
      if (data.status === 'ok' && data.task_id) {
        listenExtractProgress(data.task_id);
      } else {
        setProgressStatus('exception');
        setProgressText(data.message || '启动失败');
        message.error(data.message || '批量抽取启动失败');
        setLoading(false);
      }
    } catch {
      setProgressStatus('exception');
      setProgressText('启动失败');
      message.error('批量抽取启动失败');
      setLoading(false);
    }
  };

  return (
    <Section title="批量知识抽取">
      <p style={{ color: 'var(--ink-60)', fontSize: 13, marginBottom: 14 }}>
        对 raw/ 目录下的所有语料进行知识抽取，结果进入审核队列
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
        <Button
          type="primary"
          size="large"
          loading={loading}
          onClick={handleExtractBatch}
          icon={<BranchesOutlined />}
          style={{ flex: 1 }}
          disabled={loading}
        >
          {loading ? '抽取中...' : '执行批量抽取'}
        </Button>
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
