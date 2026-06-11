# aha 活页 · 工作约定

本目录是 aha 全站**活页**(kg-*、live、dashboard、gallery 等单文件 HTML)。
线上 = aha.yishujia.art,部署目录 = `/data/pub/p/aha/`(改完 `cp` 过去)。

## 🏛️ 路由:主页 = 博物馆,产品日志 = log.html

- **主页 `/` = `museum.html`(人类美术馆)**。nginx `index museum.html …`;`index.html` 是指向 museum 的重定向。**别把任何东西命名成 index.html 当内容页**。
- **产品日志 = `log.html`**(原 home.html→曾误命名 index.html,现定为 log.html;`home.html` 仍 0 秒重定向到它)。它不是首页,是**人机交互产品日志**:收录所有活页,可按**分区 / 时间**双排序(时间读 `data/pages.json`,现为文件近似时间、待校正)。
- 凡新做的活页都要**登记进 `log.html`**(原 [[aha-home-index-rule]]),登记时带日期。

## ⚠️ 设计系统是强制的,不是建议

**写或改任何页面前,先按设计系统来。** 三个权威文件:

| 文件 | 作用 |
|---|---|
| `css/aha-kit.css` | **唯一可信来源**:所有 token + 组件。改样式只改这里。 |
| `design-system.html` | 样板间:19 板块的 live 实例 + 可照抄片段(线上 /design-system.html)。 |
| `DESIGN-SYSTEM.md` | 书面规范 + "如何新建一张活页"清单。 |

基调:**低唤醒 · 画先到 · 安静的纸**。暖纸 `#f4f1ea` + 赭石 `#b0673a`,Noto Serif/Sans SC + JetBrains Mono。

## 5 条铁律(违反=返工)

1. **同源不重造**——颜色/字号/间距一律用 `var(--token)`;**页内永不写 `:root{}` 或十六进制**。这是活页变丑变乱的头号原因。
2. **画先到**——界面退到作品之后:克制留白、低对比、赭石只点一处。
3. **赭石是信号不是装饰**——只有可交互/当前/强调才染 `--accent`。**重点信息**用 `.note.accent`(浅赭石卡,可加 `.k` 圆点标签);**全站禁止用左侧竖条 `border-left:Npx solid accent` 做强调**(TOC/引言/note 一律不用)。
4. **数字诚实**——异步先 `.loading`/`.skel`,空数据走 `.empty`,**绝不留白或填假数据**;推断 vs 考据用虚线/实线区分。
5. **手感一致**——可交互元素:hover 染赭石 + 微抬升,`:focus-visible` 焦点环,缓动统一 `var(--ease)`。

## 新建/改页必做

1. `<head>` 只引两行(顺序固定):
   ```html
   <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
   <link rel="stylesheet" href="css/aha-kit.css">
   ```
2. 用语义 class 搭骨架:`.page → .pagehead → .sec`;列表用 `.grid`+`.card`,图表用 `.bar`/inline-SVG,状态用 `.chip`,数字用 `.stat`/`.tbl .num`,表单用 `.field/.input/.select/.slider`,反馈用 `.toast`/`.scrim+.modal`。页面专属微调放独立 `<style>` 且**只用 `var(--…)`**。
   - **统一顶栏/底栏**:body 末尾必挂 `<script src="js/aha-chrome.js"></script>`(自动注入顶栏 + 底栏:备案号 浙ICP备2021038972号-8 / 出品 浙江大学国际设计研究院)。有大 hero 的页用 `<body data-no-top>` 只要底栏。备案/出品只在 `aha-chrome.js` 一处维护。
   - 顶栏 brand `aha.art` → **museum.html(主页)**;右侧"产品日志"→ **log.html**(都由 aha-chrome.js 自动给)。页面里手写的"回首页"指 museum、"看全部/日志"指 log.html;别再写 index.html/home.html 当内容链接。
3. 认领一类**活页原型**再填内容:Live 数据页 / KG 详情页 / Dashboard / Gallery。
4. 迁旧页 = 删掉页内 `:root{…}` 退化变量 → 引 `aha-kit.css` → 类名换成语义 class。范本见 `kg-style-live.html`。
5. 完工两件事:① 登记进 `log.html` 产品日志;② `cp` 到 `/data/pub/p/aha/`。

> 拿不准某个组件长什么样,先开 `design-system.html` 照抄,别自己发明。
