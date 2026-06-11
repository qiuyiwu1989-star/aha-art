# aha 统一用户体系设计

> 现状:账号(注册/登录/会话)已建;museum 有匿名 uid+行为(mu_event)+口味(mu_taste 2D)+收藏(mu_collection)+用户展(mu_exhibition)+人设(mu_persona)。
> 而 kg-me / kg-me-algo / kg-taste / museum#hall=mine 是**同一套"我"的四个面**,各自跑 demo/localStorage,彼此割裂。
> 本设计=把它们统一成一套**账号绑定、活数据驱动**的用户体系。

## 0. 一句话架构
**一个账号 → 一份审美档案(12维向量) → 驱动 你在这里/为你推荐/我的收藏与展 → 越逛越准。**
所有"我"都挂在 `mu_user.uid`(已可注册);所有行为/向量/收藏从活库(works 的 worldview+language7+affect)实时算。

## 1. 要并入用户体系的东西(五面合一)
| 现状页/概念 | 角色 | 并入后 |
|---|---|---|
| 账号(已建) | 身份 | `me.html` 总入口;cookie 会话;匿名可认领 |
| **kg-me** 审美档案 | **核心档案** | 12维向量点云 + 本命画家 + 门派原型 + 三盏灯,**绑账号、用真数据** |
| **kg-taste** 你在这里 | 定位+冷启动 | 选画对→落世界观平面→就近推荐艺术家;结果写入档案 |
| **kg-me-algo** 推荐内核 | 算法 | reward 内核(契合×惊奇 d*)给"为你推荐"feed |
| **museum #hall=mine** 我的 | 我的收藏/展 | 收藏(mu_collection)+我的展(collections owner=我)+阅读记录,统一进 me.html |
| **kg-gallery** 生成图库 | **我的创作** | 生成图绑 uid → "我的生成"进 me.html;全部生成 → 管理后台模块(见 §5.1) |

## 5.1 生成图库:分"我的"与"管理后台"(本次新增)
**现状缺口**:`ark_gen_server.py` 把每张生成图存进**全局静态 `data/kg_gen_gallery.json`**(无 uid、删除靠口令);
而 `mu_generation` 表**早有 `uid` 列 + (uid,ts) 索引却没被用上**。kg-gallery.html 是单一全局池,既非"我的"也非受控后台。
**改造**(与"页面=库的投影"原则一致,静态 JSON 几十万会崩):
- **库为准源**:`save_record` 出图即 `INSERT mu_generation(id,uid,file,prompt,meta,rating,backtest)`;uid 从前端 meta 带上(localStorage `aha_uid`/登录态);JSON 过渡期可并写,之后停。
- **我的(用户端)**:`/cat/gen?scope=mine` 只返我的 uid 的生成 → me.html「我的创作」标签 + kg-gallery.html 个人模式。评分/删除限本人。
- **管理后台**:dashboard 新增「生成图库」模块 `/admin/m/gen`,跨用户全量;治理=评分/回测/删除(走 admin 鉴权,不再用明文口令)/**优选入馆**(把好图提升为展品候选)。
- 旧 kg-gallery.html(全局展示版)保留,逐步切到"我的"。

## 2. 数据模型(在现有 mu_* 上扩展)
- `mu_user`:已加 email/pwhash/nickname。
- **`mu_profile`(新)**:uid PK,`vec float8[12]`(审美重心μ),`spread float8`(离散),`n int`,`archetype text`(48门派),`soulmate text`(本命 canon artist_id),`lights jsonb`(三盏灯:顿悟密度/审美成长/安静感),updated。
  - **12维 = worldview(2:再现-表现/结构-感知) + language7(构图/空间/造型/光影/色彩/笔触/边缘) + affect(3:VAD)** —— 正好与 works.vlm 同构,用户μ=其engaged作品向量的(加权)均值。
- `mu_event`:行为日志(已有);新增按 work_id 关联(见③)。
- `mu_collection`/`mu_exhibition`/`collections(owner_uid)`:我的收藏与展(已有/已扩展)。
- `mu_taste`:旧 2D 口味,保留兼容(=vec 的 worldview 两维)。

## 3. 关键打通:行为 → 作品向量(当前缺口)
mu_event.target_id 现在是 COS url 或旧文本键,**与 works.work_id(bigint) 不同源**。要算 12维档案,必须把行为关联到作品向量。
**方案**:art.html/画廊 log_event 时**额外带 work_id**(它有 /cat 数据,知道 bigint id);后端 mu_event 加 `work_id bigint` 列。这样 engaged 作品 → works.vlm 向量 → 算 μ。旧 url 事件靠 cos_key 反查兜底。

## 4. 审美档案怎么算(kg-me 落地)
1. 用户 like/dwell 作品 → 取该作品 12维向量(worldview2+lang7+vad3)。
2. μ = engaged 作品向量的滑动加权均值(like 权重>dwell);spread=离散度。**双时间尺度**:此刻心情(近20件) vs 长期口味(全部)。
3. **本命画家** = canon artists 里 12维向量与 μ 最近者(canon.lore 有 lang/wv/affect)。
4. **门派原型** = 48门派(kg-me-types)里最近者。
5. **三盏灯** = 顿悟密度(接受的跳跃)/审美成长(spread 扩张)/安静感(dwell 时长),从 mu_event 算。
6. **d\* 自学习**:从用户接受的"惊奇跳跃"反推个人惊奇带(kg-me-algo 的核心)。

## 5. 推荐内核(kg-me-algo 落地)→ "为你推荐"
候选作品打分 `reward = w1·契合(−|vec−μ|) + w2·惊奇(落在 d* 带内的距离) + w3·质量 + w4·新颖(未看过)`。
- 落地为端点 `/cat/foryou?uid=` :在 kept 里按 reward 排序返回(用 pgvector 近邻加速——已装)。
- 喂给 me.html「为你推荐」+ 画廊/展厅的个性化排序。

## 6. 页面整合
- **`me.html`(总入口,已建)** 扩成三页签:**① 审美档案**(档案卡:门派/本命/12维雷达/三盏灯/世界观坐标) **② 为你推荐**(reward feed) **③ 我的**(收藏/我的展/阅读记录)。
- kg-taste 冷启动(选画对)并入 me.html 的"校准口味"入口;结果写 mu_profile。
- 旧 kg-me/kg-me-algo/kg-taste **demo 页保留**(讲解/对外展示);me.html 是活数据版总和。
- museum #hall=mine 收藏 → 指向 me.html#我的(或保留 museum 内,但数据同源 mu_collection)。

## 7. 路线(分期)
- **一期(打通地基)**:mu_event 加 work_id + 画廊/展厅 log 带 work_id;建 `mu_profile`;写 `profile.py`(从 engaged 作品算 12维μ+本命+门派+三盏灯)。
- **二期(档案页)**:me.html ① 审美档案卡(雷达/本命/门派/世界观点),活数据。
- **三期(推荐)**:`/cat/foryou` reward 内核(pgvector)→ me.html ② 为你推荐 + 画廊个性化。
- **四期(我的+冷启动)**:me.html ③ 我的(收藏/展/记录)统一;kg-taste 选画对冷启动并入。
- **五期(生成图库分流)**:save_record 写 mu_generation(带 uid);`/cat/gen?scope=mine`+me.html「我的创作」;dashboard「生成图库」管理模块(全量+优选入馆);删除/评分转鉴权端点。
- 贯穿:匿名→注册认领;旧 demo 页不动。

## 8. 隐私
档案/行为绑 uid;登录态 cookie(HttpOnly+Secure)。用户可在 me.html 看/清空自己的数据(后续加导出/删除)。
