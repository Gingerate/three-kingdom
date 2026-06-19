"""全局进度追踪器 —— 用于长时间任务的实时进度推送"""

from __future__ import annotations
import asyncio
import logging
import time
import threading

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field


@dataclass
class ProgressState:
    """进度状态"""
    task_id: str
    stage: str = "准备中"
    current: int = 0
    total: int = 0
    message: str = ""
    done: bool = False
    error: str | None = None
    started_at: float = field(default_factory=time.time)

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return min(100, int(self.current / self.total * 100))

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "message": self.message,
            "done": self.done,
            "error": self.error,
            "elapsed": round(time.time() - self.started_at, 1),
        }


class ProgressTracker:
    """进度追踪器，支持 SSE 订阅"""

    # 任务自动清理时间（秒）：完成后的任务保留 1 小时
    AUTO_CLEANUP_SECONDS = 3600

    def __init__(self):
        self._tasks: dict[str, ProgressState] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # RLock（可重入锁）：update() → _notify() 会重入，且避免 subscribe() yield 时阻塞 worker 线程
        self._lock = threading.RLock()
        # 启动后台清理线程
        self._cleanup_thread = threading.Thread(target=self._auto_cleanup_loop, daemon=True)
        self._cleanup_thread.start()


    def create_task(self, task_id: str) -> ProgressState:
        state = ProgressState(task_id=task_id)
        with self._lock:
            self._tasks[task_id] = state
            self._subscribers[task_id] = []
        return state

    def update(self, task_id: str, *, stage: str | None = None,
               current: int | None = None, total: int | None = None,
               message: str | None = None, done: bool | None = None,
               error: str | None = None):
        with self._lock:
            state = self._tasks.get(task_id)
            if not state:
                return

            if stage is not None:
                state.stage = stage
            if current is not None:
                state.current = current
            if total is not None:
                state.total = total
            if message is not None:
                state.message = message
            if done is not None:
                state.done = done
            if error is not None:
                state.error = error

        # 通知所有订阅者（锁外执行，避免死锁）
        self._notify(task_id, state)

    def _notify(self, task_id: str, state: ProgressState):
        # 获取订阅者列表的副本，避免迭代时修改
        with self._lock:
            queues = list(self._subscribers.get(task_id, []))

        data = state.to_dict()
        for queue in queues:
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, task_id: str, timeout: float = 300):
        """异步生成器，用于 SSE 流

        Args:
            task_id: 任务 ID
            timeout: 超时时间（秒），默认 5 分钟

        注意：yield 时绝不能持有 self._lock，否则 worker 线程的 update() 会死锁。
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # 注册订阅者
        with self._lock:
            self._subscribers.setdefault(task_id, []).append(queue)

        # 先发送当前状态（锁内读取，锁外 yield）
        with self._lock:
            state = self._tasks.get(task_id)
        if state:
            yield state.to_dict()
            if state.done:
                return

        start_time = time.time()
        try:
            while True:
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    yield {"task_id": task_id, "error": "进度订阅超时", "done": True}
                    break

                remaining = timeout - elapsed
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=min(remaining, 30))
                    yield data
                    if data.get("done"):
                        break
                except asyncio.TimeoutError:
                    # 心跳：锁内读取，锁外 yield
                    with self._lock:
                        current_state = self._tasks.get(task_id)
                    if current_state:
                        yield current_state.to_dict()
        finally:
            # 清理
            with self._lock:
                subs = self._subscribers.get(task_id, [])
                if queue in subs:
                    subs.remove(queue)

    def get_state(self, task_id: str) -> ProgressState | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cleanup(self, task_id: str):
        with self._lock:
            self._tasks.pop(task_id, None)
            self._subscribers.pop(task_id, None)

    def _auto_cleanup_loop(self):
        """后台自动清理已完成的任务"""
        while True:
            time.sleep(300)  # 每 5 分钟检查一次
            self._cleanup_expired_tasks()

    def _cleanup_expired_tasks(self):
        """清理过期的已完成任务"""
        with self._lock:
            now = time.time()
            expired_ids = []
            for task_id, state in self._tasks.items():
                if state.done and (now - state.started_at) > self.AUTO_CLEANUP_SECONDS:
                    expired_ids.append(task_id)

        # 在锁外执行清理（cleanup 是幂等操作，TOCTOU 无实际影响）
        for task_id in expired_ids:
            self.cleanup(task_id)
            logger.info(f"自动清理过期任务: {task_id}")


# 全局单例
tracker = ProgressTracker()
