import { type ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title?: string;
  description?: string;
  children?: ReactNode;
}

/** 统一的空状态组件 */
export default function EmptyState({
  icon,
  title = '暂无数据',
  description,
  children,
}: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && (
        <div className="empty-state-icon">
          {icon}
        </div>
      )}
      {title && <div className="empty-state-title">{title}</div>}
      {description && <div className="empty-state-description">{description}</div>}
      {children && <div className="empty-state-action">{children}</div>}

      <style>{`
        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 60px 24px;
          text-align: center;
        }

        .empty-state-icon {
          font-size: 48px;
          color: var(--ink-20);
          margin-bottom: 16px;
          opacity: 0.6;
        }

        .empty-state-title {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 700;
          color: var(--ink-60);
          margin-bottom: 8px;
        }

        .empty-state-description {
          font-size: 13px;
          color: var(--ink-40);
          max-width: 320px;
          line-height: 1.6;
        }

        .empty-state-action {
          margin-top: 24px;
        }
      `}</style>
    </div>
  );
}
