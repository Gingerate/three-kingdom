import { createContext, useContext, useState, useRef, useCallback, type ReactNode } from 'react';
import { chatStream, type StreamEvent } from '../services/api';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  route?: string;
  subQuestions?: string[];
  isStreaming?: boolean;
}

interface ChatContextValue {
  messages: Message[];
  loading: boolean;
  streamStatus: string;
  handleSend: (text?: string) => Promise<void>;
  clearMessages: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const handleSend = useCallback(async (text?: string) => {
    // 取消上一次未完成的流
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const question = (text || '').trim();
    if (!question || loading) return;

    const controller = new AbortController();
    abortRef.current = controller;

    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

    await chatStream(
      question,
      undefined,
      (event: StreamEvent) => {
        const { node, updates } = event;
        const statusMap: Record<string, string> = {
          router: '分析问题中...',
          decompose: '分解问题中...',
          retrieve: '检索资料中...',
          grade: '筛选资料中...',
          generate: '生成回答中...',
          reflect: '检查质量中...',
          finalize: '整理完成',
          increment_retry: '重新检索中...',
        };
        setStreamStatus(statusMap[node] || '');

        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            const msg = { ...updated[last] };
            if (updates.final_answer) {
              msg.content = updates.final_answer;
              msg.isStreaming = false;
            } else if (updates.generation && !msg.content) {
              msg.content = updates.generation;
            }
            if (updates.sources) msg.sources = updates.sources;
            if (updates.route) msg.route = updates.route;
            if (updates.sub_questions) msg.subQuestions = updates.sub_questions;
            updated[last] = msg;
          }
          return updated;
        });
      },
      () => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            updated[last] = { ...updated[last], isStreaming: false };
          }
          return updated;
        });
        setLoading(false);
        setStreamStatus('');
        abortRef.current = null;
      },
      (error) => {
        // 忽略主动取消的错误
        if (error.name === 'AbortError') return;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            updated[last] = {
              ...updated[last],
              content: `发生了错误：${error.message}`,
              isStreaming: false,
            };
          }
          return updated;
        });
        setLoading(false);
        setStreamStatus('');
        abortRef.current = null;
      },
      controller.signal,
    );
  }, [loading]);

  const clearMessages = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setMessages([]);
    setLoading(false);
    setStreamStatus('');
  }, []);

  return (
    <ChatContext.Provider value={{ messages, loading, streamStatus, handleSend, clearMessages }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within ChatProvider');
  return ctx;
}
