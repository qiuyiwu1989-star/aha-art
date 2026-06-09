# aha · 人端数据模型 `Person`(方案 2 · 可落地 schema)

> 落实 [`ARCHITECTURE-v2.md`](./ARCHITECTURE-v2.md) 第 5 节。
> **公理(镜像艺术家)**:艺术家 = 在生成链上持续**产出**作品的人格源,其作品在世界观平面上形成点云;
> **用户 = 在生成链上持续**偏好**作品的消费源,其选择在同一平面上形成点云。**
> 产出侧(`kg-artist`)与消费侧(`Person`)是同一套点云渲染的两半——重心 · 离散 · 轨迹 · 漂移。

---

## 0. 一句话

> `Person` 不是"标签集合",是**坐标系里一团会随时间漂移的点**。
> 它的当前画像(重心/离散/区)由一条 **append-only 事件流**派生,因此可重算、可回放、可解释。

---

## 1. 坐标系(与艺术家、与画端共用同一套)

人端**复用** `kg-artist` 的「④ 世界观坐标」平面,**不另起炉灶**:

| 维度 | 轴 | 现有代码出处 | 取值 |
|---|---|---|---|
| **世界观平面**(L0 根) | `再现 ↔ 表现`(x)　⊥　`结构 ↔ 感知`(y) | `kg-taste` 的 `tx,ty` · `kg-artist ④` | 0..1 × 0..1 |
| **情绪环**(L3 效应) | `愉悦 valence`　×　`唤起 arousal`(VAD) | `kg-taste` 的 `tv,ta` | 0..1 × 0..1 |

> 已**弃用** V2 的「秩序-张力 / 节制-强度」两轴(V3 已把它们下放为语言/效应层),人端与艺术家页保持一致,只用上面这一面 + 一环。
> 题材母题 / 色彩 等为**派生标签**(可读、可展示),非主坐标。

---

## 2. `Person` Schema(字段级)

```jsonc
{
  "schemaVersion": "person/1",

  // ── 身份(多终端的命门:档案挂在这后面,而非浏览器) ──
  "id": "string",                 // 稳定标识:账号 id;未登录时给匿名稳定 id(可后续合并)
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601",

  // ── 当前画像(全部由 events 派生,可重算;存一份是为读取快) ──
  "profile": {
    "centroid": { "x": 0.0, "y": 0.0 },   // 世界观重心(再现-表现 ⊥ 结构-感知)
    "spread":   0.0,                        // 离散 σ:点云围绕重心的均方根半径(专一↔杂食)
    "mood":     { "v": 0.5, "a": 0.5 },     // 情绪重心(愉悦 × 唤起)
    "homeRegion": "REG.id | null",          // 最近的世界观区
    "regionOffset": { "x": 0.0, "y": 0.0 }, // 相对所属区重心的带符号偏移(镜像艺术家)
    "drift":    { "dx": 0.0, "dy": 0.0 },   // 近期漂移方向(新近重心 − 早期重心)
    "exploreAppetite": 0.5,                  // 反茧房探索胃口 0..1
    "topRegions": ["REG.id"],                // 派生可读标签
    "topThemes":  ["theme"],                 // 派生可读标签(母题)
    "n": 0                                   // 已计入的有效事件数(置信度)
  },

  // ── 轨迹(时间维度:一生的漂移,可回放) ──
  "trajectory": [
    { "t": "ISO-8601", "x": 0.0, "y": 0.0, "spread": 0.0, "n": 0 }
    // 每个窗口(如每 25 条事件 / 每周)落一个快照点;连起来 = 你的审美轨迹
  ],

  // ── 事件流(append-only · 唯一真相 · profile/trajectory 皆由它派生) ──
  "events": [
    {
      "ts": "ISO-8601",
      "type": "view|dwell|heart|unheart|door|skip|choose|reject|detail|share",
      "workId": "string",            // 作用对象(画/艺术家/风格节点)
      "opponentId": "string|null",   // choose/reject 的对手(二选一时)
      "value": 0,                    // dwell 秒数 / 其它数值
      "mode": "drift|galaxy|chroma|dwell|dial|versus|talk|...",  // 来自哪种逛法/终端
      "wv":  { "x": 0.0, "y": 0.0 }, // 该对象在世界观平面的落点(从画端取,冗余存=可离线重算)
      "aff": { "v": 0.0, "a": 0.0 }, // 该对象的情绪落点
      "device": "web|app|...",
      "daypart": "morning|...|null"
    }
  ]
}
```

**设计要点**
- `events` 是**唯一真相**;`profile` 与 `trajectory` 是它的**派生缓存**,任何时候可从 `events` 重算(这就是"可回放、可解释")。
- 每条事件**冗余存 `wv/aff` 落点**:避免派生时反查画端,且画端坐标若日后微调,旧事件仍按当时坐标可重算。
- `id` 与浏览器解耦——这是多终端的前提;匿名 id 登录后可 **merge** 进账号。

---

## 3. 事件 → 画像 派生算法

### 3.1 信号权重(沿用现有体感)
```
WEIGHT = { heart:+2.0, choose:+1.5, detail:+1.0, dwell: clamp(value/15, 0..1.5),
           view:+0.3, door:+0.6, share:+1.5,
           reject:-1.0, skip:-0.4, unheart:-2.0 }
// 负权重事件:把其落点作为"排斥锚",在重心计算里反向拉(见 3.2)
```

### 3.2 重心 `centroid`(加权 + 近期偏重)
复用 `kg-taste` 已有逻辑(近期样本权重更高 `1+i*0.25`),推广到事件流:
```
w_i = WEIGHT[type_i] · recency(i)        // recency: 越新越大,如 0.98^(rank_from_newest)
centroid.x = Σ(w_i · wv_i.x) / Σ w_i     // 负权重事件:用 (2·centroid.x − wv_i.x) 作反向锚,或直接计入负权
centroid.y = 同上
mood       = 同法对 aff.v / aff.a 求加权均值
```

### 3.3 离散 `spread` σ(新增 —— 艺术家点云有,人端补上)
```
spread = sqrt( Σ w_i · dist(wv_i, centroid)^2 / Σ w_i )   // 加权均方根半径
// 小=专一(口味集中),大=杂食(口味开阔)
```

### 3.4 区归属 `homeRegion` + 带符号偏移(镜像艺术家)
```
homeRegion   = argmin_REG  hypot(REG.cx − centroid.x, REG.cy − centroid.y)   // 已在 kg-taste 实现
regionOffset = { x: centroid.x − REG.cx, y: centroid.y − REG.cy }            // 你在区内偏向哪边
```

### 3.5 漂移 `drift` + 轨迹 `trajectory`(时间维度 —— 这是 localStorage 版完全没有的)
```
// 轨迹:每满一个窗口(N=25 事件 或 跨周)对"截至此刻的事件"算一次 centroid/spread,push 进 trajectory
// 漂移:近窗重心 − 远窗重心
drift = trajectory[last].xy − trajectory[max(0,last-K)].xy     // K 窗的位移向量
```

### 3.6 探索胃口 `exploreAppetite`
```
// 用户主动点"探索门"/接受远离重心的推荐的比例;也可由 spread 与拒绝率联合估计
exploreAppetite = f( door率, 接受远点率, spread )
```

> **增量更新**:线上每来一条事件,可只做 `centroid/spread` 的增量加权更新(O(1)),窗口边界才落 `trajectory` 快照并重算 `drift`;无需每次全量扫 `events`。全量重算只在"解释/回放/坐标系改版"时触发。

---

## 4. 从 `aha_mystar` / `localStorage` 迁移

现状:`kg-galaxy` 把 `myProfile`(由测验所选作品 `computeProfile()` 得)整包存进 `localStorage['aha_mystar']`;`kg-taste` 现算现用、不持久。
迁移策略 = **把"当前快照"转成"轨迹的第 0 点 + 种子事件",而非丢弃**:

```js
// migrateLocalToPerson(): 登录/首次联网时调用一次
function migrateLocalToPerson(personId) {
  const ms = JSON.parse(localStorage.getItem('aha_mystar') || 'null');
  if (!ms) return null;
  const now = nowISO();                       // 注:服务端给时间戳
  // 1) 把测验所选作品还原成 choose 事件(有 wv/aff 落点的就带上)
  const events = (ms.picks || ms.chosen || []).map(p => ({
    ts: now, type: 'choose', workId: p.id,
    wv: p.wv || null, aff: p.aff || null,
    mode: 'taste-quiz', device: 'web', value: 1
  }));
  // 2) 用现成快照直接落轨迹第 0 点(若 ms 里已有 tx/ty)
  const seed0 = (ms.tx != null)
    ? [{ t: now, x: ms.tx, y: ms.ty, spread: ms.spread ?? 0, n: events.length }]
    : [];
  const person = {
    schemaVersion: 'person/1', id: personId,
    createdAt: now, updatedAt: now,
    events, trajectory: seed0,
    profile: deriveProfile(events)            // 跑第 3 节算法
  };
  localStorage.setItem('aha_migrated', '1');  // 防重复迁移
  return person;                              // → POST 给服务端
}
```

要点:① 迁移**只追加不丢弃**(localStorage 快照变成事件 + 轨迹起点);② 匿名 `personId` 登录后可 `merge`;③ 服务端负责发时间戳(脚本环境 `Date.now()` 不可用,见仓库约定)。

---

## 5. 艺术家 ⟷ 用户 点云镜像表

| | 艺术家(`kg-artist` · 产出侧) | 用户(`Person` · 消费侧) |
|---|---|---|
| 是什么 | 在链上持续**产出**的人格源 | 在链上持续**偏好**的消费源 |
| 点云来自 | 他的全部**作品**落点 | 他的全部**交互事件**落点 |
| 重心 | 创作立场 | 审美质心 |
| 离散 σ | 创作幅度 | 口味宽窄(专一↔杂食) |
| 区归属 + 偏移 | 居于/跨越某世界观区 | 常驻哪个区、偏向哪边 |
| 轨迹/漂移 | 一生的风格演变 | 越逛口味怎么变(可回放) |
| 时间 | 生卒、创作期 | 注册至今的会话流 |

> 因为两侧**同坐标系**,"推荐最合你的艺术家" = 在平面里找离 `Person.centroid` 最近的艺术家点云重心(+ 按 `exploreAppetite` 给探索位)。这正是 `kg-taste` 末尾"最合我的艺术家"的服务端化、可积累版本。

---

## 6. API(并入 v1 的 Match API,人端持久化)

```
ingest(personId, event)              // 收一条事件 → append + 增量更新 profile/trajectory
getProfile(personId) -> Person.profile          // 星图/「你在这里」用
getTrajectory(personId) -> trajectory[]         // 轨迹回放
nextFor(personId, {ctx, exclude?}) -> {workId, reason, explore}   // 取最近邻 + 探索位
matchArtists(personId, {k}) -> [{artistId, score}]               // 最合你的艺术家(点云距离)
mergePersons(anonId, accountId)      // 匿名档案并入账号(跨终端/登录)
recompute(personId)                  // 从 events 全量重算(改版/解释/回放)
```

> 全部建立在第 1 节那套坐标系上;换终端、扩数据、升算法都不动坐标语义。

---

## 7. 落地顺序(给开发的最小切口)

1. **定 schema**:本文件即定义;先冻结 `person/1`。
2. **写 `deriveProfile(events)`**:第 3 节算法,纯函数、可单测(输入事件数组 → profile)。这是人端的"大脑核心"。
3. **服务端 `Person` 存储 + `ingest/getProfile`**:先 append 事件 + 增量更新,跨终端连续从这步成立。
4. **迁移钩子**:`migrateLocalToPerson()` 接上现有 `aha_mystar`,老用户无缝平移。
5. **渲染复用**:把 `kg-taste` 的平面/情绪环、`kg-artist` 的点云渲染,改成读 `getProfile/getTrajectory`——人端首页(「我的审美档案」)= 艺术家页的消费侧镜像。
