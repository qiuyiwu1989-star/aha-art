# aha.art · 独立化架构蓝图

> 把当前"静态 demo"独立成 **aha.art** 产品的总纲。
> 承接 [`ARCHITECTURE-v2.md`](./ARCHITECTURE-v2.md)(两端一坐标系)与 [`PERSON-MODEL.md`](./PERSON-MODEL.md)(人端 N(μ,Σ))。
> **核心判断:一个 Postgres(+pgvector)打天下,大脑搬到服务端,前端变薄。**

---

## 0. 现状盘点(已有的一半基建)

| 已有 | 说明 |
|---|---|
| 静态前端 | `*.html` + `data/*.json`,部署 ai.zaowuyun.com/aha,无后端 |
| 本机 Postgres `aha` 库 | artists / works / files(sha256/phash 去重 + 来源适配器),凭据 `~/.aha_pg.json` |
| COS 图床 | 桶 `aha-1254041526` 放 artworks/,凭据 `~/.aha_cos.json` |
| Python 数据管线 | 抓数据 → 算向量 → 建边(已有雏形,scripts/) |
| 浏览器内大脑 | kg-me.html 的 brain v0.6,Person 存 localStorage |

**独立化 = 把这些接成一条线,而非从零起。**

---

## 1. 核心论断:一个库三类数据

你的数据天然三类,但**不要上多套库**:

| 数据 | 存哪 | 为什么 |
|---|---|---|
| 知识图谱(艺术家/作品/谱系边/区/风格) | **Postgres** | 结构化、要关联查询 |
| 审美向量(每作品/人一个 12 维向量) | **pgvector**(Postgres 扩展) | 匹配=向量最近邻;几万条对 pgvector 是小菜,**无需单独向量数据库** |
| 作品图 | **COS + CDN** | 大文件,已有 |
| 人的档案 + 事件流 | **Postgres**(同库) | person 表 + append-only events 表 |

> 关键:整套"匹配"(人重心 → 最近作品/艺术家)= 一句 `ORDER BY vec <=> :mu`。**pgvector 把推荐的召回层变成一条 SQL。**

---

## 2. 数据库设计(Postgres + pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 画端(扩现有 artists/works)──
CREATE TABLE regions (              -- 6 个世界观区(WV1–6)
  id text PRIMARY KEY, name text, cx real, cy real);

CREATE TABLE artists (
  id text PRIMARY KEY, cn text, en text, born int, death int,
  region_id text REFERENCES regions(id), nationality text,
  centroid vector(12),              -- 作品点云重心(与人同维)
  spread real[],                    -- 各轴 std(Σ 对角)
  bio text, headline text, meta jsonb);

CREATE TABLE artworks (
  id text PRIMARY KEY, title text, artist_id text REFERENCES artists(id),
  year int, image_key text,         -- COS object key
  license text, source text,
  wv vector(2), lang vector(7), affect vector(3),
  vec vector(12),                   -- 拼好的总向量(世界观2+语言7+情绪3)
  region_id text REFERENCES regions(id),
  subjects text[], meta jsonb);

CREATE TABLE edges (                 -- 谱系/影响/对抗
  src text, dst text, rel text, why text, confidence real,
  PRIMARY KEY (src, dst, rel));

-- ── 人端(新增)──
CREATE TABLE persons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id text,                  -- 登录后绑定;匿名时 null
  mu vector(12),                    -- life 长期重心
  mu_sess vector(12),               -- sess 此刻重心
  sigma real[],                     -- 各轴 std(Σ 对角,椭球)
  d_star real, explore real,        -- 惊奇带(自学习) / 探索胃口
  aversion real[],                  -- 回避向量(负反馈语义化)
  visited jsonb, meters jsonb,      -- 区访问 / 三盏灯
  n int, created_at timestamptz, updated_at timestamptz);

CREATE TABLE events (                -- 唯一真相,画像由它派生
  id bigserial PRIMARY KEY,
  person_id uuid REFERENCES persons(id),
  ts timestamptz DEFAULT now(),
  type text,                        -- heart|skip|choose|reject|view|dwell|...
  work_id text REFERENCES artworks(id),
  pred jsonb,                       -- 推荐时的预测四项分(给自检/校准)
  mode text, device text);

-- ── 索引:召回靠它 ──
CREATE INDEX artworks_vec_idx ON artworks USING ivfflat (vec vector_cosine_ops) WITH (lists=100);
CREATE INDEX events_person_idx ON events (person_id, ts);
```

**说明**
- `persons` 的 `mu/sigma/d_star/aversion` = kg-me 里 Person v0.6 的服务端版,字段一一对应。
- `events` append-only;画像随时可从它**重放重算**(=现在前端的 `derive(events)`,移到服务端)。
- `vec` 是匹配主键;`wv/lang/affect` 分量保留,供分空间距离(dWV/dLang/dAff)与可视化。

---

## 3. 关键决定:大脑搬到服务端

现在 brain 在浏览器跑;独立后**召回必须上服务端**(几万候选不可能塞进浏览器)。

```
客户端(任意终端)            服务端 API                     Postgres+pgvector
  发事件     ───────────▶  POST /events ──── append ───▶  events
  要下一帧   ───────────▶  GET /me/next
                            ① 召回 = ANN  ◀── ORDER BY vec <=> mu ──  artworks
                            ② 打分 = 美学奖励四项 − 回避惩罚 (numpy)
                            ③ MMR 重排(多样+疲劳)
                            ④ 选 top + 探索位
              ◀─ 下一帧 + 解释 + 预测分 ─┘
```

- **召回** = pgvector ANN(SQL),候选 ~30 张。
- **打分**(顿悟/安静/信息/成长 + 负反馈) = 服务端 numpy,**brain.js 逐函数移植**。
- **画像更新** = ingest 时增量更新 `persons` 行(或定期从 events 重放)。
- 客户端变薄:只发事件、收下一帧 + 解释。

---

## 4. API 契约(两道接口,沿用 v2)

```
# Content API(画端,只读)
GET  /works?region=&artist=&page=        → 作品列表
GET  /works/:id                          → 单作品
GET  /artists/:id                        → 艺术家(含点云)
GET  /neighbors/:id?rel=                 → 谱系邻居
GET  /search?q=                          → 全局搜索

# Person API(人端)
POST /events            {type,workId,pred,mode}   → ingest,更新画像
GET  /me/profile                          → {mu,sigma,d_star,aversion,meters,门派...}
GET  /me/next?exclude=                    → {workId,reason,parts,explore}  ← 召回+打分+重排
GET  /me/artists?k=                       → 最合你的艺术家(点云最近邻)
POST /me/merge          {anonId}          → 匿名档案并入账号
GET  /s/:code                             → 分享只读档案(= 现 #s= 的服务端版)
```

**身份**:匿名优先——首次给稳定 `person_id`(cookie),不强制注册;愿意登录再 `merge`。符合"让美来找你"。

---

## 5. 仓库结构(拉出去开新仓)

```
aha.art/
  api/            FastAPI
    content.py    # Content API(读 Postgres)
    person.py     # Person API(events / profile / next)
    brain.py      # 美学奖励打分(numpy,移植自 brain.js v0.6)
    recall.py     # pgvector ANN 召回
    db.py         # 连接池 / 查询
  pipeline/       Python 数据管线
    ingest_*.py   # 各馆开放数据 → 归一化
    build_vec.py  # 算 wv/lang/affect → vec,灌库
    build_edges.py
  web/            前端(现有页面改调 API;先保持 vanilla 也行)
  db/             schema.sql + migrations + 种子数据
  infra/          nginx.conf + docker-compose.yml + deploy.sh
```

技术栈:**FastAPI(Python)** ——因为数据管线与向量数学(EMA/打分)都在 Python,pgvector 的 Python 支持好;前端保持 JS,先不引框架。

---

## 6. 迁移路径(从现在到独立,5 步)

1. **建库**:`data/*.json` → Postgres;给 works/artists 补 `vec` 列 + 装 pgvector + 建 ANN 索引。
2. **起 API**:FastAPI 读 Postgres+pgvector,把 brain.js 打分逻辑移植成 `brain.py`。
3. **改前端**:页面里 `fetch('data/*.json')` → 调 Content API;kg-me 的逛法 → `GET /me/next`。
4. **加人端**:`persons`+`events` 表 + 匿名身份;kg-me 的 localStorage → `POST /events`。**(此步=跨终端、分享ID 真正成立的硬门槛)**
5. **独立部署**:绑 **aha.art** 域名,一台 VPS 跑 nginx + API + Postgres,图走 COS+CDN。

---

## 7. 部署形态(起步够用)

```
              ┌──────── aha.art (域名) ────────┐
   用户/终端 ─▶ nginx ─┬─▶ /api/*  → FastAPI (uvicorn/gunicorn)
                       └─▶ /*      → web 静态资源
                                        │
                              Postgres + pgvector(同机或托管)
                                        │
                              COS 图床 + CDN(已有)
```

- 起步:**一台 VPS** 全装(nginx + uvicorn + Postgres)。流量上来再拆:Postgres 托管、API 多副本、CDN 全量。
- 备份:Postgres 定时快照(events 是真相,丢不得);图在 COS 天然冗余。
- 监控:接口延迟、ANN 召回耗时、每日活跃 person 数。

---

## 8. 一句话

> **aha.art = Postgres(知识图谱)+ pgvector(审美向量,召回即 SQL)+ COS(图)+ 一个 FastAPI(把 brain 搬到服务端)。** 画与人都是同坐标系里的向量,匹配=最近邻,人端 append-only 事件流跨终端跟着账号走。前端任意终端,只认两道 API。
