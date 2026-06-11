# aha 活页设计系统 · 规范

> 适用于所有文档/仪表盘型活页:`kg-*`、`dashboard`、`*-live` 等。
> 美术馆漫游体验(onboard / wander / 三扇门 / 星图)走另一层 `css/aha.css`,二者并列。
> 活的样板间:[`design-system.html`](design-system.html)。改 token/组件先看那里。

---

## 1. 设计原则

| 原则 | 含义 |
|---|---|
| **画先到** | 界面退到作品之后。版式安静,不与画争注意力。 |
| **安静的纸** | 暖纸基底 + 赭石点睛。纯白只用于卡面暖白 `--card`,低唤醒、低对比噪声。 |
| **同源不重造** | 所有颜色/字号/间距走 token,**绝不在页内重新定义退化变量**(这是当前活页变丑的根因)。 |
| **手感一致** | 可交互元素统一:hover 染赭石 + 微抬升,`:focus-visible` 焦点环可见,缓动同一条曲线。 |

---

## 2. Token(全在 `css/aha-kit.css :root`)

### 颜色 — 用语义名,不要写十六进制
- **表面**:`--paper` 页底 · `--paper-2` 凹陷 · `--card` 卡面暖白 · `--line`/`--line-soft` 描边
- **文字四阶**:`--ink` 主 · `--ink-soft` 次 · `--ink-mute` 弱 · `--ink-faint` 极弱
- **主色**:`--accent`(赭石 #b0673a)· `--accent-soft` 底 · `--accent-line` 边
- **数据三色**:`--green`(探索)· `--blue`(信息)· `--gold`(强调),各配 `*-soft`
- **语义状态**:`--ok` · `--warn` · `--rej` · `--mute`,各配 `*-soft`

### 字体族
- `--serif` Noto Serif SC → 标题、品牌、强调短句
- `--sans` Noto Sans SC → 正文、说明
- `--mono` JetBrains Mono → 标签、计数、数字、kicker、元信息

### 字阶
`--fz-display` / `--fz-h1` 25 / `--fz-h2` 19 / `--fz-h3` 16 / `--fz-body` 14 / `--fz-small` 12.5 / `--fz-tiny` 11 / `--fz-label` 10.5

### 间距 / 圆角 / 阴影 / 缓动
- 间距阶 `--s1..--s7` = 4 / 8 / 12 / 16 / 24 / 32 / 48
- 圆角 `--r-sm` 6 · `--r` 12 · `--r-lg` 16 · `--r-pill`
- 阴影 `--sh-1` 静 · `--sh-card` 抬升 · `--sh-pop` 浮层(均暖色调)
- 缓动 `--ease` = `cubic-bezier(.22,.61,.36,1)` · 时长 `--dur` .18s / `--dur-slow` .4s

---

## 3. 组件清单(class → 用途)

| Class | 用途 |
|---|---|
| `.page` / `.page.narrow` / `.wide` | 居中页壳容器 |
| `.pagehead` + `.back` `.kicker` `h1` `.sub` `.meta` | 页头五件套 |
| `.sec` + `.sec-h`(`.t` `.n` `.d`) | 区块与区块标题 |
| `.grid` / `.grid.cols-2` `.cols-4` `.tight` | 响应式卡片网格 |
| `.card` / `.card.link` / `a.card` + `.card-h`(`.nm` `.en` `.n`) `.card-note` | 卡片(可点的加 `.link`) |
| `.bar` + `.lb` `.track` `.fill` `.knob` `.val`;变体 `.green/.blue/.gold` | 指标条 |
| `.chip`(`.ok/.warn/.rej/.info/.green/.muted`) / `.tag`(`.m`) / `.badge` | 标记三件套 |
| `.stats` + `.stat`(`.num` `.u` `.lab`) | KPI 数字 |
| `.tbl` + `th/td.num` | 表格(数字列加 `.num`) |
| `.btn` / `.btn.ghost` `.pill`,`[disabled]` | 按钮 |
| `.field` + `.fl` / `.input` / `.select` / `.search` / `.slider` / `.check` / `.segwrap`+`.seg` | 表单 |
| `.toast`(`.ok/.warn/.rej`)/ `.scrim`+`.modal`(`h3` `p` `.acts`) | 反馈:通知 / 弹窗 |
| `.site-top` / `.site-foot` | 统一顶栏 / 底栏(由 `js/aha-chrome.js` 自动注入,底栏含备案号+出品) |
| `.loading` / `.empty`(`.hint`)/ `.skel` / `.fade-in` | 加载·空·骨架·入场 |
| `.note` / `.note.accent`(+ 可选 `.k` 圆点标签)/ `.rule` / `.muted` `.faint` `.serif` `.mono` | 文本块与工具类 |

**重点信息 callout**:普通说明用 `.note`(中性纸卡),强调用 `.note.accent`(浅赭石卡),需命名的重点加一行 `.k`(圆点 + mono 小标)。
**全站禁止用左侧竖条做强调**(`border-left:Npx solid var(--accent)`)——TOC、引言、note 一律不用;emphasis 来自暖底/标签,不来自竖边。

> 完整实例 + 可照抄 HTML 片段 + 5 种图表/活页原型/铁律见 **`design-system.html`**(单页网页规范,带 sticky 侧栏 TOC、滚动高亮、代码一键复制)。

### 图表(5 种,inline SVG,套 token 配色)
指标条 `.bar` · 雷达(风格指纹)· 散点(世界观平面)· 时间线(东西双带)· 关系网络(承自/影响)。
约定:**实线=考据成立,虚线=推断**;数据三色 `--green/--blue/--gold` 仅作区分,不进正文。

### 活页原型(新建先认领一类)
**Live 数据页**(fetch→卡片网格+指标条)· **KG 详情页**(单实体多段:身份+雷达+关联)· **Dashboard**(KPI 行+表格+状态色)· **Gallery**(图先到·密铺)。

---

## 4. 交互规范

- **可点元素**:hover 时 `border-color:--accent` +(卡片)`translateY(-2px)` + `--sh-card`;`.back` hover 左移 2px。
- **焦点**:依赖全局 `:focus-visible` 赭石描边——不要 `outline:none`。
- **缓动**:一律 `var(--ease)`,时长 `--dur`(状态)/ `--dur-slow`(进度条填充)。
- **动效降级**:`prefers-reduced-motion` 已全局关掉动画,自定义动效也要尊重。
- **加载流**:先渲染 `.loading`/`.skel` → 数据就位后替换为内容并加 `.fade-in`。
- **数字**:统一 `--mono` + `tabular-nums`(`.val`/`.stat .num`/`.tbl .num` 已内置)。

---

## 5. 如何新建一张活页(清单)

1. `<head>` 里只引这两行(顺序固定):
   ```html
   <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
   <link rel="stylesheet" href="css/aha-kit.css">
   ```
2. **不要**写 `:root{…}` 重定义颜色/字体——直接用 token。页面专属微调放独立 `<style>`,且只用 `var(--…)`。
3. 骨架照抄:`.page` → `.pagehead` → 若干 `.sec`(每个含 `.sec-h` + 内容)。
4. 列表/卡片用 `.grid` + `.card`;图表用 `.bar`;状态用 `.chip`;数字用 `.stat`/`.tbl .num`。
5. 异步数据:先 `.loading`,到位后 `.fade-in`;无数据走 `.empty`,绝不留空白或假数据。
6. 做完把页面登记进 [`home.html`](home.html) 索引(项目规矩),部署 `cp` 到 `/data/pub/p/aha/`。

### 迁移旧活页
把页内 `:root{--ink:…;--bg:…}` 整段删掉 → 引 `aha-kit.css` → 类名换成上表语义 class。
参考首张样板改造:`kg-style-live.html`。
