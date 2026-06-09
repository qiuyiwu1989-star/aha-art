# aha · 架构设计说明 (v1)

> aha = 一座"懂你的人类美术馆"。
> **地基不变(L1 内容层),大脑变聪明(L3 智能层),逛法千变万化(L2 体验层)。**

---

## 0. 设计目标与原则

1. **三层解耦**:数据、智能、交互彻底分开,各自独立演化。
2. **契约优先**:层与层之间只通过两个稳定接口对话(Content API / Match API),改任意一层不动其余两层。
3. **护城河集中在 L1 × L3**(数据资产 + 懂你);L2 是可实验、可丢弃、可被抄的表层。
4. **数据结构稳定**:L1 schema 定一次,内容只增不改结构。
5. **个性化双层**:既匹配"给哪一帧画",也匹配"用哪种逛法"。

---

## 1. 总架构

```
 ┌──────────────── L2 体验层(多种逛法 · 可换可加 · 插件化)─────────────────┐
 │  漂流 · 银河 · 以色觅画 · 专注单幅 · 对话策展 · 二选一 · 手机手势版 …       │
 │       ▲ 读内容 / 读匹配                              │ 发信号               │
 └───────┼──────────────────────────────────────────────┼─────────────────────┘
  Content API │                                   ingest │ Signal
 ┌───────┴────────┐                          ┌───────────▼─────────────┐
 │  L1 内容层      │ ◀──── 查内容 / 查图谱 ────│   L3 智能层(大脑)        │
 │  数据 + 知识图谱 │        Content API        │  信号 → 画像 → 匹配 → 导演 │
 │  + 打标语料      │                          └───────────┬─────────────┘
 └────────────────┘                       Match API 回灌:  │ 最佳一帧 + 该用哪种逛法
                                                            ▼  给 L2
```

**两道契约接口是整个系统的命门:**
- **Content API**(L1 提供,只读):内容怎么存、从哪来、加多少,上层不关心。
- **Match API**(L3 提供):画像怎么算、匹配多聪明,逛法不关心,只管"要下一帧 / 该用哪种逛法"。

---

## 2. L1 · 内容层(稳定地基)

**职责**:把"一幅画 + 它们之间的关系"沉淀成稳定、可查询的事实地基。

**数据模型(五层 schema,详见正文 schema 规范):**
- L0 身份与溯源:`id` · `wikidataQID`(去重主键)· `sources[]` · `status`
- L1 客观事实:`title{zh,en,original}` · `creators[]{name,ulanId,…}` · `date{display,start,century}` · `classification(AAT)` · `medium[]` · `depicts[](Iconclass)` · `movement` · `origin{place,tgnId}`
- L2 媒体与版权:`iiifManifest` · `images{full,display,thumb,lqip}` · `palette[]` · `rights{license,isPublicDomain}`(展示闸门)
- L3 策展/AI 富集:`themes[]`(受控母题词表)· `oneLiner` · `look` · `mood{valence,arousal}` · `embeddings{clip,text}` · `canonTier` · `enrichMeta`
- L4 关系/边(单独集合):`edge{a,b,type,why,confidence,evidence}`;`type ∈ influence|theme|formal|artist|movement`

> **打标语料**(用户自有)灌入 L3 富集层:母题→`themes`、情绪→`mood`、色彩、甄选→`canonTier`。

**对外契约 · Content API(只读):**
```
getWork(id)                         -> Work
list({filter?, sort?, page?, limit?}) -> { items: Work[], total }
neighbors(id, {types?, limit?})     -> Edge[]            // {to, type, why, confidence}
byColor(rgb, {limit?})              -> Work[]            // 按色彩距离排序
byTheme(theme, {sort?})             -> Work[]
byMood({valence, arousal, tol?})    -> Work[]
search(text)                        -> Work[]
stats()                             -> { total, byCategory, edges }
```

**稳定性**:结构版本化(`schemaVersion`),内容只增不改结构;上层永不直接访问存储。
**技术**:入库管线(各馆开放数据 + 打标语料 → 归一化到受控词表 → 建边 + 离线算 embedding/主色)→ 存储(Demo: JSON;产品: DB)→ Content API。
**护城河**:是(数据资产 + 打标语料 + 图谱)。

---

## 3. L3 · 智能层(大脑 · 持续变聪明)

**职责**:从用户的每次交互读懂他 → 给出最佳匹配(画 + 逛法)。

**信号模型(L2 → L3):**
```
ingest(userId, Signal)
Signal = {
  type: 'view'|'dwell'|'heart'|'unheart'|'door'|'skip'|'choose'|'reject'|'detail'|'share',
  workId,
  value?,                 // dwell 秒数 / choose 时的对手 workId 等
  mode,                   // 来自哪种逛法(drift / versus / chroma …)
  context: { ts, device, daypart, mood? }
}
// 各信号 → 母题/色彩/情绪的权重增减(heart+2, 长 dwell+, skip-, choose+/对手-)
```

**画像模型(Taste Profile):**
```
TasteProfile = {
  themes:   { [theme]: weight },     // 母题偏好
  colors:   { [hueBucket]: weight }, // 色彩偏好
  mood:     { valence, arousal },    // 情绪质心
  embedding?: number[],              // 视觉/语义向量质心
  topThemes: string[],
  exploreAppetite: 0..1,             // 反茧房探索胃口
  updatedAt
}
```

**对外契约 · Match API:**
```
ingest(userId, signal)                              // 收信号、更新画像
profile(userId)              -> TasteProfile         // 审美指纹/星图用
nextFor(userId, {context, exclude?}) -> {workId, reason}   // 今日一帧 / 漂流下一帧
rank(userId, candidates | {neighborsOf}) -> [{workId, score, explore}]  // 排序 + 反茧房探索位
matchByMood(userId, {mood|color|text}) -> Work[]     // 以心情/颜色/一句话匹配
pickMode(userId, {context}) -> modeId                // 自动选用哪种逛法
```

**导演(Director)**:`nextFor`/`matchByMood`(选内容)+ `pickMode`(选逛法)的统一调度。**默认自动匹配,用户随时可手动接管。**
**依赖**:调用 L1 Content API;从不被 L1/L2 反向依赖。
**护城河**:是(核心 = 懂你)——目前最弱、最该重投。

---

## 4. L2 · 体验层(多变 · 插件化)

**职责**:把"一帧画"以某种逛法呈现,并采集偏好信号回吐 L3。

**逛法插件契约(每个 Mode 都遵守):**
```
Mode = {
  id, label,
  device: ['mobile'|'desktop'|'both'],
  signalsEmitted: [...],                 // 它能采哪些信号(选 Mode 时参考)
  mount(rootEl, { content, match, ctx }) -> unmount()
  // 内部:用 content + match 渲染;用户操作时 match.ingest(signal)
}
```
- 读 **Content API**(原始内容/图片/图谱)+ **Match API**(下一帧/排序)。
- 向 `match.ingest` **回吐信号**。
- 互不知道彼此存在,只认两道契约。

**逛法注册表 + 选择器:**
```
registry = [drift, galaxy, chroma, dwell, dial, versus, talk, mobile, …]
进入方式:① 用户手选(hub 页)  ② match.pickMode(user, ctx) 自动匹配
```

**关键洞察**:每种逛法同时是一台"偏好传感器"——选哪些做主力,既看体验,也看**它给 L3 喂的信号干不干净**(如:二选一=强偏好信号;以色觅画=色彩偏好;停留=兴趣强度)。
**护城河**:否(会被抄,不必恋战)。

---

## 5. 数据流

**A. 一次会话(请求流):**
```
进入 → 选择器问 Director.pickMode(user, ctx) → 加载对应 Mode
     → Mode 调 match.nextFor(user) → L3 查 L1 Content → 返回最佳一帧
     → Mode 渲染(读 Content 取图/图谱)
```

**B. 学习闭环:**
```
用户操作(看/心动/停留/推门/跳过/选择)
   → Mode 发 Signal → match.ingest → 画像更新
   → 下一次 nextFor / rank 立刻反映新偏好(越用越准)
```

---

## 6. 代码结构(对现有 demo 的重构)

```
/data
  artworks.json   graph.json        # L1 内容(Demo);产品期 → DB + API
/js
  content.js      # L1 · Content API(数据加载 + 查询 + 图谱)
  brain.js        # L3 · Match API(信号 + 画像 + 匹配 + 导演)
  ui.js           # 共享渲染(artframe / ambient 等)
  app.js          # 启动:注册表 + 选择器
  modes/
    drift.js  galaxy.js  chroma.js  dwell.js  dial.js
    versus.js talk.js    mobile.js  …          # L2 · 各逛法插件
```

**现状映射**:当前 `core.js` 把三层混在一起——
- `loadData / BY / ADJ / 查询` → 拆到 `content.js`(L1)
- `taste / score / rankedNeighbors / bestNext / topThemes` → 拆到 `brain.js`(L3)
- `artframe` + ambient → `ui.js`
- 现有各页 → `modes/*`

---

## 7. 技术与部署

| 阶段 | L1 内容 | L3 智能 | L2 体验 |
|---|---|---|---|
| **Demo(现在)** | 浏览器内 JSON | 客户端 + localStorage 画像 | 静态页 + nginx |
| **产品** | 后端 DB + Content API 端点;离线算 embedding/主色 | **服务端画像 + 匹配**(跨设备、画像归服务端 = 护城河) | Web + **微信小程序** 客户端,共用同两道 API |

**契约版本化**:`schemaVersion`、`ContentAPI vN`、`MatchAPI vN`;Mode 锁定所用 API 版本。

---

## 8. 路线图(按"稳定 → 护城河 → 实验")

1. **锁 L1**:schema 定到字段级 + 打标语料对接格式(导出即可灌入)。
2. **砸 L3**:把"玩具版 taste vector"升级成真引擎(多信号融合 + embedding 相似 + 反茧房 + 导演选逛法)——**差异化重心**。
3. **收敛 L2**:从 15 种收敛到 2–3 主力(手机版 + 漂流/对话 + 以色),其余作实验插件。

---

## 9. 为什么这样设计更好

- **更好理解**:地基(L1)/ 大脑(L3)/ 逛法(L2),一句话讲清。
- **更好开发**:三层并行、互不阻塞;加逛法不碰数据,升算法不碰交互。
- **更好防御**:护城河集中在 L1 × L3;L2 被抄无所谓。
- **更好生长**:语料越多 L1 越厚 · 用得越久 L3 越准 · 点子越多 L2 越丰富——**三条增长线各自复利**。
