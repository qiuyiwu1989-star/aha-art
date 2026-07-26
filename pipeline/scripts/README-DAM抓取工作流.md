# DAM 数据抓取工作流（造物云·创意设计团队）

> 固定下来不遗忘。dam.alimq.com 的生成区数据 = 造物云「创意设计」团队的工作流出图历史。
> 维护人：邱懿武 + AI。最后更新 2026-06-17。

## 一句话

每天凌晨 3 点，自动从造物云 API 把「创意设计」团队**全部工作流**最近 3 天的新执行
拉进 Postgres（`gen_run` + `gen_file`）并存图到 COS，随后为新图建 CLIP 向量供语义检索。

## 范围（重要）

- **只抓「创意设计」这一个团队**（teamId `67ee23b636ff1d9725e06306`，token 即绑定此团队）。
- token 账号名下虽有 16 个客户团队（波司登/苏泊尔/海尔…），但此 token 只能访问创意设计一个。
  **其他客户暂不抓**，需要时各团队要各自的 token。
- 工作流清单 = **动态枚举**，不再硬编码。新建的工作流会被自动覆盖，不会漏。

## 涉及的东西

| 件 | 位置 |
|---|---|
| 同步脚本 | `aha-art/pipeline/scripts/sync_zwy_daily.py` |
| 建向量脚本 | `aha-art/pipeline/scripts/compute_clip.py` |
| 定时任务 | 用户 crontab：`0 3 * * *`（见下） |
| 日志 | `aha-art/pipeline/logs/sync_daily.log`、`compute_clip.log` |
| 数据库 | Postgres `aha` 库，表 `gen_run` / `gen_file`（`source='zaowuyun_team'`）；凭据 `~/.aha_pg.json` |
| 对象存储 | 腾讯云 COS 桶 `aha-1254041526`，前缀 `artworks/_generated/zaowuyun/<工作流名>/`；凭据 `~/.aha_cos.json` |
| API | `https://app.zaowuyun.com`，Bearer token 写在脚本顶部 `TOKEN` |
| 前端/后端 | 见 dam.alimq.com（`dam-api.service` :8091 + nginx vhost） |

## 工作流清单怎么来的（这次的修复）

```
GET https://app.zaowuyun.com/api/workflow/metadata?page=1&limit=500
Authorization: Bearer <TOKEN>
```

- 返回该团队**当前全部工作流**（约 149 个）。**注意必须带 `limit`**，默认只返回 24 条。
- 脚本里 `list_workflows()` 负责枚举，过滤 `isDeleted`，取 `id` 字段（== `workflowId`）。
- `displayName` 可能是字符串，也可能是 `{"zh-CN":..,"en-US":..}`，已统一取中文名。

> 历史坑：以前硬编码 52 个工作流 → 28 个有执行的工作流共 222 次执行从未进库，且新建
> 工作流永远漏。改成动态枚举后此问题根除。

## 每条执行怎么变成数据

1. `POST /api/workflow/executions/search` `{workflowId, pagination, orderBy:startTime DESC}` 翻页取执行列表。
   - 执行项里的 `workflowId` 字段其实是**执行 UUID**（= `gen_run.instance_id`）。
2. 按 `startTime` 截断：默认只要最近 `--days` 天内的（`--all` 时不截断，扫到底）。
3. 已存在的 `instance_id` 跳过（幂等）。
4. 提取 prompt / 输入图 / 模型 / 参数 → 写 `gen_run`。
5. 下载输出图 → sha256 去重 → phash → 存 COS → 写 `gen_file`（`q_status='pending'`）。

## 常用命令

```bash
cd aha-art/pipeline/scripts

python3 sync_zwy_daily.py --list            # 只看当前工作流清单，不抓
python3 sync_zwy_daily.py --days 3           # 抓最近 3 天（cron 用这个）
python3 sync_zwy_daily.py --all --workers 6  # 一次性全量回扫补漏（幂等，可随时跑）
python3 compute_clip.py --workers 8          # 给生成区新图建 CLIP 向量(gen_clip)
python3 compute_clip_media.py --workers 8    # 给素材库新图建 CLIP 向量(zaowuyun_media.embedding_vec;无待办则秒退)
```

> 云端两个库:**生成区**(gen,`gen_file`/`gen_clip`,~9.6万,本脚本每日抓的工作流出图) 与
> **素材库**(media,`zaowuyun_media.embedding_vec`,~1.3万,一次性抓的设计素材)。前端 dam.alimq.com 顶部切换。
> 后端 `dam_api.py`:生成区端点 `/stats /browse /search /similar`;素材库同名加 `media/` 前缀,返回结构对齐。
> 两库检索都用 **ViT-B/32**;素材库自动分类用的是另一个模型(clip-vit-base-patch16),**不能**当检索向量。
> 素材库 HNSW 索引 = `idx_zwy_media_embed`(cosine)。

## 统一入库管线 `ingest_pipeline.sh`（每张新图都走的流水线）

所有入库图片走**同一条幂等流水线**,封装在 `scripts/ingest_pipeline.sh`,每步只处理"还没做过"的图(增量):

```
1) 抓取   sync_zwy_daily.py  — 拉新执行 + 去重(sha256/phash) + 存COS + 写库
2) 分类   classify_gen.py    — workflow+prompt 规则 → category
3) 主色   gen_color.py / zwy_color.py — COS ?imageAve 免下载算 ave_rgb+hue
4) 向量   compute_clip.py / compute_clip_media.py — ViT-B/32 → embedding_vec
5) 质检   (TODO 待定"达标"标准:最小尺寸/废图/近重复折叠 → q_status)
```

手动补跑(幂等,可随时):`bash ingest_pipeline.sh`(可 `DAYS=30 bash ingest_pipeline.sh` 扩天数)。

## 定时任务（用户 crontab）

```cron
3 3 * * * PATH=/usr/local/bin:/usr/bin:/bin HOME=/home/ubuntu \
  bash /home/ubuntu/users/qiuyiwu/aha-art/pipeline/scripts/ingest_pipeline.sh \
  >> /home/ubuntu/users/qiuyiwu/aha-art/pipeline/logs/ingest_pipeline.log 2>&1
```

每天 3:03 跑统一管线。新数据当天即分类/主色/向量齐全,可被语义搜 / 以图搜图 / 找同色命中。
（旧的 sync→clip 三段链已并入本管线,crontab 里以注释保留。）

## 健康检查（隔段时间瞄一眼）

```bash
tail -50 aha-art/pipeline/logs/sync_daily.log        # 看每天新增多少条
# DB 当前量：
psql -d aha -c "select count(*) from gen_run  where source='zaowuyun_team';"
psql -d aha -c "select count(*) from gen_file where source='zaowuyun_team';"
```

- 对账：API 侧执行总数 ≈ `POST executions/search` 每个工作流的 `total` 之和；
  与 `gen_run` 计数对比，差值应趋近 0（图片下载失败会让 gen_file 略少于应有，可重跑补）。
- 已知历史坑：`compute_clip.py` 必须用 **ViT-B/32**（512 维）对齐查询端，且要写
  `gen_clip.embedding_vec`（pgvector），不能只写 `embedding`（bytea）。
