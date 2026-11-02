# aha · 懂你的人类美术馆

> **让美,来找你 · art that finds you**
> 同一批人类公共领域名画 + 同一张知识图谱,千人千面地重排成"懂你"的画廊。

aha 把整部美术史结构化成一个**坐标系**:每幅画、每位艺术家、乃至每个**用户**,都是同一空间里的一个向量点。推荐不是"找最像你的",而是"找最能让你『原来如此』的"。

---

## 仓库结构

```
aha-art/
  web/         前端 —— 90+ 静态页面 + 数据 + 样式
    *.html       体验页(逛法)与知识图谱页(kg-*)
    data/        知识图谱 JSON(艺术家/作品/谱系/向量)
    js/ css/     脚本与样式
    img/         作品图(本地;生产走 COS,已 gitignore)
    vendor/      第三方库
  pipeline/    Python 数据管线(抓数据 → 算向量 → 建边 → 灌库)
  docs/        架构文档
```

## 跑起来(本地)

```bash
cd web
python3 -m http.server 8080
# 首页导航:    http://localhost:8080/home.html
# 我的审美档案: http://localhost:8080/kg-me.html
# 知识图谱中枢: http://localhost:8080/kg-v2.html
```

## 几个核心入口

| 页面 | 是什么 |
|---|---|
| `home.html` | 全部体验导航(消费端 + 知识图谱) |
| `kg-v2.html` | 知识图谱 V2 中枢(世界观→题材→语言→感知→画外音→风格 生成因果链) |
| `kg-me.html` | 我的审美档案 —— 把用户做成与艺术家同构的向量点云(美学奖励推荐内核 v0.6) |
| `kg-me-types.html` | 审美门派图鉴(6 门派 × 8 亚型 = 48 原型) |
| `kg-me-algo.html` | 推荐内核算法流程图 |
| `kg-galaxy.html` | 风格星辰大海(3D 关系网) |

## 架构

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 三层解耦(内容 / 智能 / 体验)
- [`docs/ARCHITECTURE-v2.md`](docs/ARCHITECTURE-v2.md) — 两端一坐标系(画 / 人 同构)
- [`docs/PERSON-MODEL.md`](docs/PERSON-MODEL.md) — 人端数据模型 `N(μ,Σ)`
- [`docs/ARCHITECTURE-standalone.md`](docs/ARCHITECTURE-standalone.md) — **独立化蓝图**(Postgres + pgvector + FastAPI + COS)

## 部署

**现状(静态)**:任意静态托管即可。
- 推荐 **Cloudflare Pages**:连本仓自动部署,自带全球 CDN + 免费 HTTPS,绑 `aha.art`。
- 或自有服务器:nginx 指向 `web/` + certbot 签证书。
- 图片:`web/img/` 不进 git,生产从 **COS + CDN** 提供。

**目标(后端)**:见 `docs/ARCHITECTURE-standalone.md` —— Postgres(知识图谱)+ pgvector(审美向量,召回即 SQL)+ FastAPI(把推荐大脑搬到服务端)。

---

*aha 是一个独立产品。核心论点:美可以被结构化、被定位、被生成——而每个人,都是这空间里独一无二的一个点。*

## 性能优化候选

本轮优化与验收见 [性能预览说明](docs/performance-preview.md) 和 [第三批验收](docs/batch-3-verification.md)。新增读取接口仍需接入正式后端，不能直接发布前端或把 SSH 预览适配器用于生产。
