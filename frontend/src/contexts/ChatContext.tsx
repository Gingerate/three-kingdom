import { createContext, useContext, useState, useRef, useCallback, type ReactNode } from 'react';
import { chatStream, getSessions, getSessionHistory, type StreamEvent, type SessionInfo } from '../services/api';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  route?: string;
  subQuestions?: string[];
  isStreaming?: boolean;
  completedNodes?: string[];
  currentNode?: string;
  timestamp?: number;
}

interface ChatContextValue {
  messages: Message[];
  loading: boolean;
  streamStatus: string;
  sessionId?: string;
  sessions: SessionInfo[];
  handleSend: (text?: string) => Promise<void>;
  clearMessages: () => void;
  loadSessions: () => Promise<void>;
  switchSession: (sessionId: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const loadingRef = useRef(loading);
  const sessionIdRef = useRef(sessionId);

  // 保持 ref 与 state 同步
  loadingRef.current = loading;
  sessionIdRef.current = sessionId;

  const handleSend = useCallback(async (text?: string) => {
    // 取消上一次未完成的流
    if (abortRef.current) {
      // 先结束上一条流式消息的状态
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated.length - 1;
        if (last >= 0 && updated[last].role === 'assistant' && updated[last].isStreaming) {
          updated[last] = { ...updated[last], isStreaming: false };
        }
        return updated;
      });
      abortRef.current.abort();
      abortRef.current = null;
      setLoading(false);
      setStreamStatus('');
    }

    const question = (text || '').trim();
    if (!question || loadingRef.current) return;

    const controller = new AbortController();
    abortRef.current = controller;

    setMessages((prev) => [...prev, { role: 'user', content: question, timestamp: Date.now() }]);
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'assistant', content: '', isStreaming: true, timestamp: Date.now() }]);

    await chatStream(
      question,
      sessionIdRef.current,
      (event: StreamEvent) => {
        // 捕获后端返回的 session_id
        if (event.session_id && !sessionIdRef.current) {
          setSessionId(event.session_id);
        }
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

        // 追踪管线节点进度
        const pipelineNodes = ['router', 'decompose', 'retrieve', 'grade', 'generate', 'reflect'];
        if (pipelineNodes.includes(node)) {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated.length - 1;
            if (last >= 0 && updated[last].role === 'assistant') {
              const msg = { ...updated[last] };
              // 当前节点之前的所有节点标记为已完成
              const nodeIdx = pipelineNodes.indexOf(node);
              msg.completedNodes = pipelineNodes.slice(0, nodeIdx);
              msg.currentNode = node;
              updated[last] = msg;
            }
            return updated;
          });
        }

        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            const msg = { ...updated[last] };
            if (updates.final_answer) {
              msg.content = updates.final_answer;
              msg.isStreaming = false;
            } else if (updates.generation) {
              // 重试时 generation 会更新，始终同步最新内容
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
        // 仅当自己仍是当前活跃流时清理状态（防止旧流回调干扰新流）
        if (abortRef.current !== controller) return;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated.length - 1;
          if (last >= 0 && updated[last].role === 'assistant') {
            updated[last] = {
              ...updated[last],
              isStreaming: false,
              completedNodes: ['router', 'decompose', 'retrieve', 'grade', 'generate', 'reflect'],
              currentNode: undefined,
            };
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
        // 仅当自己仍是当前活跃流时清理状态
        if (abortRef.current !== controller) return;
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
  }, []);

  const clearMessages = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setMessages([]);
    setLoading(false);
    setStreamStatus('');
    setSessionId(undefined);
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const data = await getSessions(50);
      setSessions(data.sessions || []);
    } catch {
      // 静默失败
    }
  }, []);

  const switchSession = useCallback(async (sid: string) => {
    if (loadingRef.current) return;
    try {
      const data = await getSessionHistory(sid);
      const historyMessages: Message[] = (data.messages || []).flatMap((m: any) => {
        const result: Message[] = [];
        if (m.question) result.push({ role: 'user', content: m.question });
        if (m.answer) result.push({ role: 'assistant', content: m.answer, sources: m.sources || [] });
        return result;
      });
      setMessages(historyMessages);
      setSessionId(sid);
      setStreamStatus('');
    } catch {
      // 静默失败
    }
  }, []);

  return (
    <ChatContext.Provider value={{ messages, loading, streamStatus, sessionId, sessions, handleSend, clearMessages, loadSessions, switchSession }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within ChatProvider');
  return ctx;
}
