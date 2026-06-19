import { CheckOutlined } from '@ant-design/icons';

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

interface ChatPipelineProgressProps {
  completedNodes?: string[];
  currentNode?: string;
}

/** 聊天管线进度条 —— 水墨风格节点指示器 */
export default function ChatPipelineProgress({ completedNodes = [], currentNode }: ChatPipelineProgressProps) {
  return (
    <div className="pipeline-progress">
      {PIPELINE_STEPS.map((step, i) => {
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
      `}</style>
    </div>
  );
}
