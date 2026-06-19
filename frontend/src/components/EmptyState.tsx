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
    </div>
  );
}
