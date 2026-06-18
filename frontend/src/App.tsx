import { useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { MessageOutlined, NodeIndexOutlined, DatabaseOutlined, BookOutlined } from '@ant-design/icons';
import ChatPage from './pages/ChatPage';
import GraphPage from './pages/GraphPage';
import DataPage from './pages/DataPage';
import WikiPage from './pages/WikiPage';

/* ── 胶片颗粒 ── */
function FilmGrain() {
  return <div className="film-grain" />;
}

/* ── 暗角 ── */
function Vignette() {
  return <div className="vignette" />;
}

/* ── 漂浮粒子 ── */
function Particles() {
  const particles = useMemo(() => {
    return Array.from({ length: 18 }, (_, i) => ({
      id: i,
      left: `${Math.random() * 100}%`,
      size: 1.5 + Math.random() * 2.5,
      duration: 18 + Math.random() * 24,
      delay: Math.random() * 20,
      opacity: 0.15 + Math.random() * 0.25,
    }));
  }, []);

  return (
    <div className="particles">
      {particles.map((p) => (
        <div
          key={p.id}
          className="particle"
          style={{
            left: p.left,
            bottom: '-10px',
            width: p.size,
            height: p.size,
            animationDuration: `${p.duration}s`,
            animationDelay: `${p.delay}s`,
          }}
        />
      ))}
    </div>
  );
}

/* ── 水墨山影 ── */
function InkLandscape() {
  return (
    <div className="ink-landscape">
      <svg viewBox="0 0 1440 180" preserveAspectRatio="none" fill="none">
        {/* 远山 — 最淡，移动最多 */}
        <path
          className="ink-layer"
          d="M0 180 L0 110 Q80 50 200 90 Q320 130 440 70 Q520 30 640 60 Q760 95 880 45 Q1000 0 1120 40 Q1240 75 1360 25 L1440 50 L1440 180 Z"
          fill="#c5c0b6"
          opacity="0.35"
        />
        {/* 中山 */}
        <path
          className="ink-layer"
          d="M0 180 L0 130 Q140 80 300 115 Q460 145 620 95 Q780 50 940 85 Q1100 120 1260 70 Q1360 45 1440 75 L1440 180 Z"
          fill="#b0aa9e"
          opacity="0.28"
        />
        {/* 近山 — 最深，几乎不动 */}
        <path
          className="ink-layer"
          d="M0 180 L0 150 Q200 115 400 140 Q600 160 800 130 Q1000 100 1200 125 Q1350 140 1440 120 L1440 180 Z"
          fill="#9e9889"
          opacity="0.22"
        />
        {/* 底部渐变遮罩 */}
        <rect y="160" width="1440" height="20" fill="url(#fade-bottom)" />
        <defs>
          <linearGradient id="fade-bottom" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f7f3ec" stopOpacity="0" />
            <stop offset="100%" stopColor="#f7f3ec" stopOpacity="1" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}

/* ── 顶栏 ── */
function TopBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const currentKey = location.pathname.split('/')[1] || 'chat';

  const navItems = [
    { key: 'chat', icon: <MessageOutlined />, label: '智能问答', path: '/chat' },
    { key: 'wiki', icon: <BookOutlined />, label: '知识沉淀', path: '/wiki' },
    { key: 'graph', icon: <NodeIndexOutlined />, label: '知识图谱', path: '/graph' },
    { key: 'data', icon: <DatabaseOutlined />, label: '数据管理', path: '/data' },
  ];

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <div className="topbar-seal">三</div>
        <span className="topbar-title">三国知识库</span>
      </div>
      <div className="topbar-divider" />
      <nav className="topbar-nav">
        {navItems.map((item) => (
          <button
            key={item.key}
            className={`topbar-link ${currentKey === item.key ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>
      <div className="topbar-spacer" />
    </header>
  );
}

/* ── App ── */
function App() {
  return (
    <BrowserRouter>
      {/* 电影质感层 */}
      <FilmGrain />
      <Vignette />
      <Particles />

      {/* 主界面 */}
      <TopBar />
      <div className="main-content">
        <InkLandscape />
        <div className="page-wrapper">
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/wiki" element={<WikiPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
