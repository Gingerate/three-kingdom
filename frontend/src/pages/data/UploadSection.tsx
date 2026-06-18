import { Upload, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { uploadAndIngest } from '../../services/api';
import Section from './Section';

interface UploadSectionProps {
  loading: boolean;
  setLoading: (loading: boolean) => void;
  setProgress: (progress: number) => void;
  setProgressStatus: (status: 'active' | 'success' | 'exception') => void;
  setStage: (stage: string) => void;
  setProgressText: (text: string) => void;
  onSuccess?: () => void;
}

/** 上传文件区域 */
export default function UploadSection({
  loading,
  setLoading,
  setProgress,
  setProgressStatus,
  setStage,
  setProgressText,
  onSuccess,
}: UploadSectionProps) {
  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess: onUploadSuccess, onError } = options;
    setLoading(true);
    setProgress(0);
    setProgressStatus('active');
    setStage('上传中');

    try {
      const data = await uploadAndIngest(file as File);

      if (data.status === 'ok') {
        setProgress(100);
        setProgressStatus('success');
        setProgressText('入库完成');
        message.success(`${data.filename} 已入库，${data.result.chunks} 个文本块`);
        onUploadSuccess?.(data);
        onSuccess?.();
      } else {
        throw new Error(data.message || '上传失败');
      }
    } catch (err: any) {
      setProgressStatus('exception');
      setProgressText('入库失败');
      message.error(err.message || '上传失败');
      onError?.(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Section title="上传文件">
      <Upload.Dragger
        name="file"
        customRequest={handleUpload}
        accept=".txt,.md,.pdf,.epub,.docx"
        showUploadList={false}
        disabled={loading}
        style={{
          background: 'var(--bg-base)',
          borderColor: 'var(--border)',
          borderRadius: 'var(--r-md)',
        }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined style={{ color: 'var(--vermilion)', fontSize: 40 }} />
        </p>
        <p style={{ color: 'var(--ink-80)', fontSize: 14 }}>点击或拖拽文件到此处</p>
        <p style={{ color: 'var(--ink-40)', fontSize: 12 }}>
          支持 .txt .md .pdf .epub .docx
        </p>
      </Upload.Dragger>
    </Section>
  );
}
