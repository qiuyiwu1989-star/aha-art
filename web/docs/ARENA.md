# 美学竞技场 · 产品说明方案

> 页面：`gen-rate.html`（线上 https://aha.yishujia.art/gen-rate.html）
> 后端：`pipeline/catalog_api.py`（/cat，端口 8094）
> 立项：2026-06-17 · 出品 浙江大学国际设计研究院

---

## 一、它是什么

把“给生成图打分”这件事，做成一个**美学竞技场**：用户通过一轮轮 **AB 对决**（两张图二选一）为我们海量的 AI 生成图投票；系统用 **Bradley-Terry** 把投票聚合成可信排名，同时**既排单张图、也排背后的“做法”**（workflow / 模型 / prompt 策略）。每打完一轮，用户拿到一张**“审美评审报告”**——照见自己的眼光与口味，可分享。

一句话：**用户来照镜子，我们顺便筛出好图、好做法、好评审。**

## 二、为什么这么做

- **目标**是“筛选出好的做法”。绝对 1–5 分一致性差、分布塌缩、难校准；成对比较一致性高得多，是 LMSYS Chatbot Arena / WildVision / 文生图 arena 的共识做法。
- **机制选型**：成对投票 → 拟合 Bradley-Terry（顺序无关、更稳，LMSYS 2023.12 起用它）→ 输出 Elo 风格分 + 置信区间。Elo 仅作实时展示的近似。
- **成就感**是留存与增长的钩子：把对决的副产品（用户口味、眼光）变成给用户的主奖励。

## 三、三方都赢（同一批投票，三样产出）

| 角色 | 得到什么 |
|---|---|
| 用户 | “审美评审报告”：眼光分、口味倾向、独特一票、贡献，可炫耀、想再玩 |
| 产品 | 图榜（挑成品）+ 做法榜（定生产策略），外加评审口味数据 |
| 机制 | 评审被自洽地排序（眼光榜），好眼光可加权抗噪，数据越投越干净 |

## 四、页面形态：三模式 + 结论卡

沿用全站“安静的纸”设计系统（aha-kit.css），无 emoji、只用 token、图标走 AHAIcons。

1. **对决（默认主推）**：两图同框，点左 / 点右 / 难分高下(tie) / 都不行(both_bad)；键盘 `←` `→` 选边、`空格` 平局。Prompt/workflow 默认折叠（画先到）。**回合制**：每 12 场触发结论卡。
2. **速评**：保留现有单图 1–5 分 + 文字反馈，做冷启动与粗筛（淘汰明显差的）。
3. **榜单**：三 tab —— 图榜 / 做法榜 / 评审眼光榜；含人评 vs AI 相关性 + 反馈流。

**结论卡（审美评审报告）**，只用能诚实算出的信号：
- **眼光分**：你的选择与全局 BT 共识的一致率（“你的眼光与大众一致度 87%”）。
- **你 vs AI**：每场比两图的 VLM 质量分，算一致率，并高亮“你和 AI 分歧、后续 BT 证明你对”的场次。
- **口味倾向（轻量）**：对你选为胜者的图，聚合色调(hue)、做法(workflow)、VLM 四轴(美感/技法/构图/连贯)对比全局 → “你更看重构图、偏爱暖色调”。
- **独特一票**：你偏爱但全局排名低的那张（配图）。
- **贡献**：对决场数、帮排了多少图 / 分清多少做法。
- **分享**：复制带 `?u=` 的链接（一期）；canvas 海报对齐 me.html 的 `buildCard`（后续）。

## 五、数据与诚实边界

- arena 可选图 27,270 张（口径同 `/gen/rate/next`：role=output、未 rejected、artist 平台 + 造物云油画）。
- **关键约束**：生成图的 `gen_file.vlm` 只有质量标注（category/composite/scores{aesthetic,technical,composition,coherence}）+ hue，**没有** real 画作的 12 维审美 schema。所以**本期不做**完整“门派 / 本命画家”结论（那需要先给生成图补 12 维 VLM 标注，列为“未来桥”）。结论卡只用上面能可靠算出的信号；数据稀疏处显空态，不编假数。

## 六、数据模型与接口

新表 `gen_battle(id, rater, left_key, right_key, left_inst, right_inst, winner, session, created_at)`，winner ∈ left/right/tie/both_bad。保留旧 `gen_rating`（双轨）。

| 接口 | 作用 |
|---|---|
| `GET /gen/battle/next?rater=&session=` | 智能配一对（低曝光优先 / 有 Elo 后偏向接近） |
| `POST /gen/battle?...&winner=` | 记一场对决 |
| `GET /gen/arena?limit=` | 图榜 + 做法榜 + 评审眼光榜 + 人评vsAI |
| `GET /gen/battle/summary?rater=&session=` | 结论卡数据 |

Bradley-Terry 用纯 Python 不动点迭代实现（无新依赖），读时计算；量大再转离线脚本。

---

# 开发计划（分步执行）

> 原则：每步可独立验证、可回滚；先打通后端对决闭环，再前端，再结论卡，最后部署。

### 步骤 1 · 后端对决闭环（建表 + BT + next/post/arena）
- 建 `gen_battle` 表 + 索引（手工 DDL）。
- `catalog_api.py` 加 `bt_scores()` helper + `/gen/battle/next`、`POST /gen/battle`、`/gen/arena`。
- 验证：curl next 出两图 → post 几场 → arena 出 BT 图榜/做法榜/眼光榜。

### 步骤 2 · 前端三模式骨架（先把对决跑通）
- 重写 `gen-rate.html`：设计系统化 + 模式切换 + 对决模式（键盘 + 回合制）。
- 速评模式保留旧逻辑、换类名。
- 验证：浏览器能连打对决、切模式、移动端单列、无 emoji/报错。

### 步骤 3 · 结论卡 + 分享
- 后端 `/gen/battle/summary`；前端结论卡（眼光/你vsAI/口味/独特一票/贡献）+ 复制分享。
- 验证：12 场弹卡、字段非空、稀疏显空态。

### 步骤 4 · 榜单完善 + 收尾部署
- 榜单三 tab 接 `/gen/arena`，BT 分 + 置信徽章。
- 登记 `log.html`（带日期）；`cp` 到 `/data/pub/p/aha/`；重启 `aha-catalog.service`。
- 端到端验证 + 诚实校验。

### 未来桥（本期不做）
- 给 `gen_file` 补 12 维审美 VLM 标注 → 接 `_profile_aha.py`，结论卡升级为完整“门派 / 本命画家”。
- 眼光加权 BT（眼光回灌为票权）。
- canvas 分享海报。

---

## 改版记录 · 2026-06-17（续）

1. **Artist 艺术家 1.0 独立产品皮**：`gen-rate.html` / `arena-method.html` 手写 `<header class="site-top">`（品牌字标 Artist + 艺术家 + 1.0 胶囊 + 赭石点；顶栏副标“美学竞技场”，独立产品感）。`aha-chrome.js` 检测到页面已有 `.site-top` 时只补底栏、不重注顶栏（其 CSS 仍无条件注入，故复用 `.site-top` 底座）。`aha-kit.css` 补 `--accent-deep`、`--latin`（Source Serif 4）。
2. **评分方法论页 `arena-method.html`**：把整套算法写清楚（资格 → 配对 → 对决记录 → Bradley-Terry 数学 → 图榜/做法榜 → 眼光 → 人评vsAI → 口味 → 诚实边界）。竞技场顶栏与 idbar 都有入口。
3. **登录打通用户体系**：同源 cookie 会话。前端 `fetch('/api/me/whoami',{credentials:'include'})`——登录则身元 = `uid`、显示昵称；未登录用本机 `aha_uid`（与 me.html 同一 localStorage key，无则生成）。`rater` 一律传 uid；去掉手填名。后端新增 `_rater_names()` 用 `mu_user` 把 uid 解析成昵称（回退原串），用于 `/gen/arena` 与 `/gen/leaderboard`。
   - **架构关键**：对决走 `/cat`（8094 catalog_api），登录走 `/api`（8093 `aha-art-demo/ark_gen_server.py`，`cookie_uid` 读 `aha_sess`）。两服务**共用同一 Postgres**，前端拿到 uid 直接传给 `/cat` 即可，无需跨服务调用。
