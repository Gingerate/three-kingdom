import { createContext, useContext, useState, useRef, useCallback, useEffect, type ReactNode } from 'react';
import { API_BASE, cancelTask } from '../services/api';

/** 任务类型 */
export type TaskType = 'extract' | 'ingest';

/** 单个任务状态 */
export interface TaskState {
  taskId: string;
  type: TaskType;
  loading: boolean;
  progress: number;
  stage: string;
  message: string;
  status: 'active' | 'success' | 'exception' | 'cancelled';
  startedAt: number;
}

interface TaskCallbacks {
  /** 任务成功完成时回调 */
  onComplete?: () => void;
}

interface TaskContextValue {
  /** 获取指定类型的任务状态 */
  getTask: (type: TaskType) => TaskState | undefined;
  /** 启动任务监听（接收到 task_id 后调用） */
  startListening: (type: TaskType, taskId: string, callbacks?: TaskCallbacks) => void;
  /** 取消任务 */
  cancel: (type: TaskType) => Promise<void>;
  /** 设置任务加载状态（API 调用阶段） */
  setTaskLoading: (type: TaskType, loading: boolean) => void;
  /** 重置任务状态 */
  resetTask: (type: TaskType) => void;
}

const TaskContext = createContext<TaskContextValue | null>(null);

export function TaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Record<string, TaskState>>({});
  // SSE 连接引用，key = task type
  const esRefs = useRef<Record<string, EventSource>>({});
  // 当前监听的 taskId，用于检测组件重挂时是否需要重新连接
  const listeningTaskIds = useRef<Record<string, string>>({});
  // 任务回调，key = task type
  const callbacksRef = useRef<Record<string, TaskCallbacks>>({});

  // 组件卸载时清理所有 SSE 连接
  useEffect(() => {
    return () => {
      Object.values(esRefs.current).forEach((es) => es.close());
      esRefs.current = {};
    };
  }, []);

  /** 更新指定任务的状态 */
  const updateTask = useCallback((type: TaskType, updates: Partial<TaskState>) => {
    setTasks((prev) => ({
      ...prev,
      [type]: { ...prev[type], ...updates } as TaskState,
    }));
  }, []);

  /** 建立 SSE 连接监听任务进度 */
  const startListening = useCallback((type: TaskType, taskId: string, callbacks?: TaskCallbacks) => {
    // 关闭旧连接
    if (esRefs.current[type]) {
      esRefs.current[type].close();
    }

    listeningTaskIds.current[type] = taskId;
    callbacksRef.current[type] = callbacks ?? {};

    // 初始化任务状态
    setTasks((prev) => ({
      ...prev,
      [type]: {
        taskId,
        type,
        loading: true,
        progress: 0,
        stage: '启动中',
        message: '正在连接...',
        status: 'active',
        startedAt: Date.now(),
      },
    }));

    const es = new EventSource(`${API_BASE}/ingest/progress/${taskId}`);
    esRefs.current[type] = es;

    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        es.close();
        delete esRefs.current[type];
        return;
      }
      try {
        const data = JSON.parse(e.data);

        setTasks((prev) => {
          const current = prev[type];
          if (!current || current.taskId !== taskId) return prev;
          return {
            ...prev,
            [type]: {
              ...current,
              progress: data.percent || 0,
              stage: data.stage || '',
              message: data.message || '',
            },
          };
        });

        if (data.done) {
          const finalStatus = data.cancelled ? 'cancelled' : data.error ? 'exception' : 'success';
          setTasks((prev) => {
            const current = prev[type];
            if (!current || current.taskId !== taskId) return prev;
            return {
              ...prev,
              [type]: {
                ...current,
                loading: false,
                progress: data.error ? current.progress : 100,
                status: finalStatus,
                message: data.error || data.message || '',
              },
            };
          });
          es.close();
          delete esRefs.current[type];
          // 成功完成时触发回调
          if (finalStatus === 'success') {
            callbacksRef.current[type]?.onComplete?.();
          }
          delete callbacksRef.current[type];
        }
      } catch (err) {
        console.error('[TaskContext] SSE 解析失败:', err);
      }
    };

    es.onerror = () => {
      es.close();
      delete esRefs.current[type];
      setTasks((prev) => {
        const current = prev[type];
        if (!current || current.taskId !== taskId) return prev;
        return {
          ...prev,
          [type]: {
            ...current,
            loading: false,
            status: 'exception',
            message: '连接中断',
          },
        };
      });
    };
  }, []);

  /** 取消任务 */
  const cancel = useCallback(async (type: TaskType) => {
    const task = tasks[type];
    if (!task || !task.loading) return;

    try {
      await cancelTask(task.taskId);
    } catch {
      // 忽略取消请求的错误
    }

    // 关闭 SSE
    if (esRefs.current[type]) {
      esRefs.current[type].close();
      delete esRefs.current[type];
    }

    updateTask(type, {
      loading: false,
      status: 'cancelled',
      message: '已取消',
    });
  }, [tasks, updateTask]);

  /** 设置任务加载状态（用于 API 调用阶段，尚未获得 task_id） */
  const setTaskLoading = useCallback((type: TaskType, loading: boolean) => {
    if (loading) {
      setTasks((prev) => ({
        ...prev,
        [type]: {
          taskId: '',
          type,
          loading: true,
          progress: 0,
          stage: '启动中',
          message: '正在启动任务...',
          status: 'active',
          startedAt: Date.now(),
        },
      }));
    } else {
      updateTask(type, { loading: false });
    }
  }, [updateTask]);

  /** 重置任务状态 */
  const resetTask = useCallback((type: TaskType) => {
    // 关闭 SSE
    if (esRefs.current[type]) {
      esRefs.current[type].close();
      delete esRefs.current[type];
    }
    delete listeningTaskIds.current[type];
    setTasks((prev) => {
      const next = { ...prev };
      delete next[type];
      return next;
    });
  }, []);

  const getTask = useCallback((type: TaskType) => tasks[type], [tasks]);

  return (
    <TaskContext.Provider value={{ getTask, startListening, cancel, setTaskLoading, resetTask }}>
      {children}
    </TaskContext.Provider>
  );
}

export function useTask() {
  const ctx = useContext(TaskContext);
  if (!ctx) throw new Error('useTask must be used within TaskProvider');
  return ctx;
}
