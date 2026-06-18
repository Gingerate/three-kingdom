"""全局进度追踪器 —— 用于长时间任务的实时进度推送"""

from __future__ import annotations
import asyncio
import time
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

    def __init__(self):
        self._tasks: dict[str, ProgressState] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def create_task(self, task_id: str) -> ProgressState:
        state = ProgressState(task_id=task_id)
        self._tasks[task_id] = state
        self._subscribers[task_id] = []
        return state

    def update(self, task_id: str, *, stage: str | None = None,
               current: int | None = None, total: int | None = None,
               message: str | None = None, done: bool | None = None,
               error: str | None = None):
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

        # 通知所有订阅者
        self._notify(task_id, state)

    def _notify(self, task_id: str, state: ProgressState):
        for queue in self._subscribers.get(task_id, []):
            try:
                queue.put_nowait(state.to_dict())
            except asyncio.QueueFull:
                pass

    async def subscribe(self, task_id: str):
        """异步生成器，用于 SSE 流"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(task_id, []).append(queue)

        # 先发送当前状态
        state = self._tasks.get(task_id)
        if state:
            yield state.to_dict()
            if state.done:
                return

        try:
            while True:
                data = await queue.get()
                yield data
                if data.get("done"):
                    break
        finally:
            # 清理
            subs = self._subscribers.get(task_id, [])
            if queue in subs:
                subs.remove(queue)

    def get_state(self, task_id: str) -> ProgressState | None:
        return self._tasks.get(task_id)

    def cleanup(self, task_id: str):
        self._tasks.pop(task_id, None)
        self._subscribers.pop(task_id, None)


# 全局单例
tracker = ProgressTracker()
