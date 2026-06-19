# Design — 三国知识库

A locked design system for this app. Every page redesign reads this file before
emitting code. Do not regenerate per page — extend or amend this file when the
system needs to grow.

## Genre
editorial

## Macrostructure family
- 内容页（Chat / Wiki / Graph）: Long Document — 卷轴式阅读，信息逐段展开
- 应用页（Data / Review / Crawl）: Workbench — 工具台式布局，功能优先

## Theme — Almanac（年鉴风格）

灵感来源：古代年鉴、历书、史籍。温暖的深象牙纸张，低饱和朱砂红点缀，
发丝线分隔，慷慨留白。移除一切"装饰性噪音"（胶片颗粒、漂浮粒子、暗角），
仅保留水墨山影作为唯一的环境氛围层。

- `--color-paper`   oklch(96% 0.006 80)    /* 深象牙 — 宣纸 */
- `--color-paper-2` oklch(100% 0 0)        /* 纯白 — 卡片 */
- `--color-paper-3` oklch(93% 0.008 80)    /* 凹陷区 */
- `--color-ink`     oklch(18% 0.005 60)    /* 墨黑 — 正文 */
- `--color-ink-2`   oklch(38% 0.005 60)    /* 次要文字 */
- `--color-ink-3`   oklch(52% 0.005 60)    /* 辅助文字 */
- `--color-ink-4`   oklch(72% 0.006 80)    /* 占位符/禁用 */
- `--color-rule`    oklch(88% 0.008 80)    /* 发丝线 */
- `--color-rule-2`  oklch(92% 0.006 80)    /* 淡发丝线 */
- `--color-accent`  oklch(48% 0.14 30)     /* 朱砂红 */
- `--color-accent-2 oklch(55% 0.12 30)     /* 浅朱砂 */
- `--color-accent-bg oklch(48% 0.02 30)    /* 朱砂淡底 */
- `--color-green`   oklch(50% 0.06 160)    /* 青石绿 */
- `--color-focus`   oklch(48% 0.14 30)     /* 焦点环 — 朱砂 */

## Typography
- Display: LXGW WenKai, weight 700, style normal
- Body:    LXGW WenKai, weight 400
- Mono:    "Consolas", "Monaco", monospace
- Display tracking: 0.06em
- Type scale: text-display = clamp(1.75rem, 3vw, 2.25rem)

## Spacing
4-point named scale. Values in tokens.css. Use var(--space-*) never raw values.

## Motion
- Easings: cubic-bezier(0.22, 1, 0.36, 1) named --ease-out
- Reveal pattern: fade + subtle slide (≤ 12px)
- Reduced-motion fallback: opacity-only, ≤ 150ms
- 动画原则：安静、有序、不喧哗。一个入场动画胜过三个。

## Microinteractions stance
- Silent success — 不使用庆祝性 toast
- Hover delay 0ms · Focus delay 0ms
- 所有交互元素必须有 8 状态：default / hover / focus-visible / active / disabled / loading / error / success

## CTA voice
- Primary: 实心朱砂，圆角 var(--radius-sm)，13px 文字
- Secondary: 发丝线边框，透明底，hover 时朱砂边框

## Per-page allowances
- 内容页（Chat/Wiki）: 可使用水墨山影 SVG 作为环境层
- 应用页（Data/Review/Crawl）: 不使用环境装饰，功能优先

## What pages MUST share
- 顶栏品牌印章 + 文字
- 朱砂红点缀色及其使用比例（≤ 5% per viewport）
- LXGW WenKai 字体
- CTA 按钮风格（圆角、padding、字号）
- 页面头部节奏（标题 + 间距 + 发丝线底边）

## What pages MAY differ on
- 内容页可使用更慷慨的 padding 和段落间距
- 应用页可使用更紧凑的表格和工具栏布局
- Wiki 阅读器可使用特殊的排版规则（h1 左边线、hr 菱形装饰等）
