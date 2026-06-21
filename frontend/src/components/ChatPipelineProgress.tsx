import { CheckOutlined, ReloadOutlined } from '@ant-design/icons';

interface PipelineStep {
  key: string;
  label: string;
}

const PIPELINE_STEPS: PipelineStep[] = [
  { key: 'router', label: '分析' },
  { key: 'decompose', label: '分解' },
  { key: 'retrieve', label: '检索' },
  { key: 'grade', label: '筛选' },
  { key: 'generate', label: '生成' },
  { key: 'reflect', label: '审查' },
];

/** 重试时的管线步骤（插入改写 query 步骤） */
const RETRY_PIPELINE_STEPS: PipelineStep[] = [
  { key: 'rewrite_query', label: '改写' },
  { key: 'retrieve', label: '检索' },
  { key: 'grade', label: '筛选' },
  { key: 'generate', label: '生成' },
  { key: 'reflect', label: '审查' },
];

interface ChatPipelineProgressProps {
  completedNodes?: string[];
  currentNode?: string;
  retryCount?: number;
}

/** 聊天管线进度条 —— 水墨风格节点指示器 */
export default function ChatPipelineProgress({ completedNodes = [], currentNode, retryCount = 0 }: ChatPipelineProgressProps) {
  // 重试时使用精简步骤（插入改写 query 步骤）
  const steps = retryCount > 0 ? RETRY_PIPELINE_STEPS : PIPELINE_STEPS;

  return (
    <div className="pipeline-progress">
      {steps.map((step, i) => {
        const isCompleted = completedNodes.includes(step.key);
        const isCurrent = currentNode === step.key;
        const isActive = isCompleted || isCurrent;

        return (
          <div key={step.key} className="pipeline-step-wrapper">
            {/* 连接线 */}
            {i > 0 && (
              <div className={`pipeline-connector ${isCompleted ? 'active' : ''}`} />
            )}
            {/* 节点 */}
            <div className={`pipeline-step ${isCompleted ? 'completed' : isCurrent ? 'current' : ''}`}>
              {isCompleted ? (
                <CheckOutlined className="pipeline-check" />
              ) : (
                <span className="pipeline-dot" />
              )}
            </div>
            {/* 标签 */}
            <span className={`pipeline-label ${isActive ? 'active' : ''}`}>
              {step.label}
            </span>
            {/* 审查节点：显示重试轮次 */}
            {step.key === 'reflect' && retryCount > 0 && (
              <span className="pipeline-retry">
                <ReloadOutlined className="pipeline-retry-icon" />
                第{retryCount + 1}轮
              </span>
            )}
          </div>
        );
      })}

      <style>{`
        .pipeline-progress {
          display: flex;
          align-items: center;
          gap: 0;
          padding: 8px 0;
          user-select: none;
        }

        .pipeline-step-wrapper {
          display: flex;
          align-items: center;
          gap: 0;
        }

        .pipeline-connector {
          width: 20px;
          height: 1px;
          background: var(--color-rule);
          transition: background 0.3s ease;
        }

        .pipeline-connector.active {
          background: var(--color-ink-4);
        }

        .pipeline-step {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--color-paper-2);
          border: 1.5px solid var(--color-rule);
          transition: all 0.3s ease;
          flex-shrink: 0;
        }

        .pipeline-step.completed {
          background: var(--color-ink-2);
          border-color: var(--color-ink-2);
        }

        .pipeline-step.current {
          border-color: var(--color-accent);
          box-shadow: 0 0 0 3px var(--color-accent-bg);
          animation: pulse-ring 1.5s ease-in-out infinite;
        }

        .pipeline-check {
          font-size: 9px;
          color: var(--color-paper-2);
        }

        .pipeline-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--color-ink-5);
        }

        .pipeline-step.current .pipeline-dot {
          background: var(--color-accent);
          animation: dot-pulse 1.2s ease-in-out infinite;
        }

        .pipeline-label {
          font-family: var(--font-display);
          font-size: 11px;
          color: var(--color-ink-5);
          margin-left: 3px;
          margin-right: 6px;
          transition: color 0.3s ease;
          white-space: nowrap;
        }

        .pipeline-label.active {
          color: var(--color-ink-3);
        }

        @keyframes pulse-ring {
          0%, 100% { box-shadow: 0 0 0 3px var(--color-accent-bg); }
          50% { box-shadow: 0 0 0 5px var(--color-accent-bg); }
        }

        @keyframes dot-pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.4); opacity: 0.7; }
        }

        .pipeline-retry {
          display: inline-flex;
          align-items: center;
          gap: 2px;
          margin-left: 4px;
          padding: 1px 6px;
          border-radius: 8px;
          background: var(--color-accent-bg);
          font-family: var(--font-display);
          font-size: 10px;
          color: var(--color-accent);
          white-space: nowrap;
        }

        .pipeline-retry-icon {
          font-size: 9px;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
