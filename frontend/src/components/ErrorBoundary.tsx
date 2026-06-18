import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button, Result } from 'antd';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * React Error Boundary
 * 捕获子组件的渲染错误，防止整个应用白屏
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary] 捕获到渲染错误:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          background: 'var(--bg-base)',
        }}>
          <Result
            status="error"
            title="页面渲染出错"
            subTitle={
              <div style={{ color: 'var(--ink-60)', fontSize: 14 }}>
                <p>抱歉，页面遇到了一个意外错误。</p>
                {this.state.error && (
                  <details style={{ marginTop: 12, textAlign: 'left' }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--ink-40)' }}>
                      查看错误详情
                    </summary>
                    <pre style={{
                      marginTop: 8,
                      padding: 12,
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--r-sm)',
                      fontSize: 12,
                      overflow: 'auto',
                      maxHeight: 200,
                    }}>
                      {this.state.error.message}
                    </pre>
                  </details>
                )}
              </div>
            }
            extra={[
              <Button key="retry" onClick={this.handleReset}>
                重试
              </Button>,
              <Button key="reload" type="primary" onClick={this.handleReload}>
                刷新页面
              </Button>,
            ]}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
