import { useEffect, useRef, useState } from 'react';

interface InkProgressProps {
  percent: number;
  stage?: string;
  message?: string;
  status?: 'active' | 'success' | 'exception';
}

/** 水墨风格进度条 —— 墨迹生长 + 飞白纹理 */
export default function InkProgress({ percent, stage, message, status = 'active' }: InkProgressProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const displayPercentRef = useRef(0);
  const animFrameRef = useRef<number>(0);
  const [displayPercent, setDisplayPercent] = useState(0);

  // 平滑过渡到目标百分比（使用 useRef + requestAnimationFrame）
  useEffect(() => {
    const animate = () => {
      const diff = percent - displayPercentRef.current;
      if (Math.abs(diff) < 1) {
        displayPercentRef.current = percent;
        setDisplayPercent(percent);
        return;
      }
      displayPercentRef.current += diff * 0.15;
      setDisplayPercent(displayPercentRef.current);
      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [percent]);

  // 绘制墨迹进度条
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d')!;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    // 清空
    ctx.clearRect(0, 0, w, h);

    // 绘制背景宣纸纹理
    drawPaperTexture(ctx, w, h);

    // 绘制墨迹进度
    const progressWidth = (displayPercent / 100) * w;
    if (progressWidth > 0) {
      drawInkProgress(ctx, progressWidth, h, status);
    }
  }, [displayPercent, status]);

  const isSuccess = status === 'success';
  const isException = status === 'exception';

  return (
    <div className="ink-progress">
      <div className="ink-progress-header">
        {stage && (
          <span className="ink-progress-stage">{stage}</span>
        )}
        <span className="ink-progress-percent">
          {isSuccess ? '完成' : isException ? '失败' : `${Math.round(displayPercent)}%`}
        </span>
      </div>

      <div className="ink-progress-track">
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: '100%', display: 'block' }}
        />
        {/* 墨滴装饰 */}
        {displayPercent > 0 && displayPercent < 100 && (
          <div
            className="ink-progress-drop"
            style={{ left: `${displayPercent}%` }}
          />
        )}
      </div>

      {message && (
        <div className="ink-progress-message">{message}</div>
      )}

      <style>{`
        .ink-progress {
          margin: 8px 0;
        }

        .ink-progress-header {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin-bottom: 6px;
        }

        .ink-progress-stage {
          font-family: var(--font-display);
          font-size: 13px;
          font-weight: 600;
          color: var(--color-accent);
          letter-spacing: 0.05em;
        }

        .ink-progress-percent {
          font-family: var(--font-display);
          font-size: 13px;
          color: var(--color-ink-3);
          font-variant-numeric: tabular-nums;
        }

        .ink-progress-track {
          position: relative;
          height: 12px;
          background: var(--color-paper-2);
          border: 1px solid var(--color-rule);
          border-radius: 2px;
          overflow: hidden;
        }

        .ink-progress-drop {
          position: absolute;
          top: 50%;
          transform: translate(-50%, -50%);
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--color-ink);
          opacity: 0.6;
          animation: drop-pulse 1.2s ease-in-out infinite;
          pointer-events: none;
          z-index: 2;
        }

        .ink-progress-message {
          font-family: var(--font-body);
          font-size: 12px;
          color: var(--color-ink-4);
          margin-top: 4px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        @keyframes drop-pulse {
          0%, 100% { opacity: 0.4; transform: translate(-50%, -50%) scale(1); }
          50% { opacity: 0.8; transform: translate(-50%, -50%) scale(1.3); }
        }
      `}</style>
    </div>
  );
}

/** 绘制宣纸纹理背景 */
function drawPaperTexture(ctx: CanvasRenderingContext2D, w: number, h: number) {
  // 基底
  ctx.fillStyle = 'rgba(247, 243, 236, 0.5)';
  ctx.fillRect(0, 0, w, h);

  // 纤维纹理
  ctx.strokeStyle = 'rgba(200, 190, 175, 0.15)';
  ctx.lineWidth = 0.5;
  for (let i = 0; i < 20; i++) {
    const y = Math.random() * h;
    ctx.beginPath();
    ctx.moveTo(0, y);
    for (let x = 0; x < w; x += 8) {
      ctx.lineTo(x, y + (Math.random() - 0.5) * 2);
    }
    ctx.stroke();
  }
}

/** 绘制墨迹进度 */
function drawInkProgress(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  status: 'active' | 'success' | 'exception'
) {
  const color = status === 'exception' ? '#8b4049' : status === 'success' ? '#5c7a6e' : '#1a1a1a';

  // 主墨迹 —— 不规则边缘
  ctx.beginPath();
  ctx.moveTo(0, 0);

  // 上边缘（毛糙）
  for (let x = 0; x <= width; x += 3) {
    const noise = Math.random() * 2 - 1;
    const edgeNoise = x < 8 ? (8 - x) * 0.5 : 0;
    ctx.lineTo(x, 1 + noise + edgeNoise);
  }

  // 右边缘（墨锋）
  const tipX = width;
  ctx.lineTo(tipX, height * 0.2);
  ctx.quadraticCurveTo(tipX + 3, height * 0.5, tipX, height * 0.8);

  // 下边缘（毛糙）
  for (let x = width; x >= 0; x -= 3) {
    const noise = Math.random() * 2 - 1;
    const edgeNoise = x < 8 ? (8 - x) * 0.5 : 0;
    ctx.lineTo(x, height - 1 + noise - edgeNoise);
  }

  ctx.closePath();

  // 墨色填充
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.85;
  ctx.fill();
  ctx.globalAlpha = 1;

  // 飞白效果（干笔留白）
  const dryBrushCount = Math.floor(width / 15);
  ctx.strokeStyle = 'rgba(247, 243, 236, 0.4)';
  ctx.lineWidth = 1;

  for (let i = 0; i < dryBrushCount; i++) {
    const x = Math.random() * width * 0.95;
    const y1 = 2 + Math.random() * 2;
    const y2 = height - 2 - Math.random() * 2;

    // 只在中间区域画飞白
    if (x > 10 && x < width - 5) {
      ctx.beginPath();
      ctx.moveTo(x, y1);
      // 飞白是不规则的短横线
      const lineLen = 3 + Math.random() * 8;
      const drift = (Math.random() - 0.5) * 2;
      ctx.lineTo(x + lineLen, y1 + drift);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(x + 2, y2);
      ctx.lineTo(x + 2 + lineLen, y2 + drift);
      ctx.stroke();
    }
  }

  // 墨点飞溅（进度前端）
  if (width > 15) {
    ctx.fillStyle = color;
    for (let i = 0; i < 3; i++) {
      const splashX = width - 5 + Math.random() * 10;
      const splashY = Math.random() * height;
      const r = 0.5 + Math.random() * 1;
      ctx.globalAlpha = 0.3 + Math.random() * 0.3;
      ctx.beginPath();
      ctx.arc(splashX, splashY, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
}
