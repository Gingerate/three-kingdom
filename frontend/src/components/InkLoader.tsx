/** 水墨风格加载动画 —— 墨滴晕染 */
export default function InkLoader({ size = 32 }: { size?: number }) {
  return (
    <div className="ink-loader" style={{ width: size, height: size }}>
      <div className="ink-drop" />
      <div className="ink-drop delay-1" />
      <div className="ink-drop delay-2" />

      <style>{`
        .ink-loader {
          position: relative;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }

        .ink-drop {
          position: absolute;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--ink-100);
          opacity: 0;
          animation: ink-spread 1.4s ease-in-out infinite;
        }

        .ink-drop.delay-1 {
          animation-delay: 0.2s;
        }

        .ink-drop.delay-2 {
          animation-delay: 0.4s;
        }

        @keyframes ink-spread {
          0% {
            opacity: 0;
            transform: scale(0);
          }
          30% {
            opacity: 0.6;
            transform: scale(1);
          }
          60% {
            opacity: 0.3;
            transform: scale(1.8);
          }
          100% {
            opacity: 0;
            transform: scale(2.5);
          }
        }
      `}</style>
    </div>
  );
}
