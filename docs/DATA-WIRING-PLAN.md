# aha 数据打通 + 后台建设规划

> 起因：现已有 **Postgres(15万件,V2标注+worldview+质量)** + **COS对象存储** + **管理后台**。
> 而历史的 kg-* 知识结构页、museum/art 消费页，**多数还在吃 119–282 件的静态 demo JSON**，与活数据断开。
> 本规划=把"该打通的数据"系统性接上，并把后台建成完整管理中枢。

## 0. 铁则
1. **唯一真源 = Postgres + COS**；所有页面是它的**下游投影**。
2. **旧 demo 页一律不破坏、原样保留**（作为存档/回退）。活数据版**新建**：要么 copy 一份改数据源，要么重做；命名加 `-live` 或并入新页。
3. **投影只读**：对外/知识页只读投影；**修改只在后台**（内）写库，再重投影。
4. **一处投影、多处消费**：建一个投影层（导出脚本 + /cat/ API），把活库变成各页需要的形状,可重跑。

## 1. 数据资产盘点（真源在库里的）
- `works`：V2 标注(media/subject/subject_tags/style/style_mix/reading/language7{7×v}/affect{vad,anchor,channels}/voiceover/fused/objects/allegory) + **worldview{wv,x,y}** + quality(composite+分项) + identify + status + exhibited + anno_import。
- `artists`(2989) / `artist_alias` / `styles`(32规范风格) / `work_subjects`。
- `files`(指纹 sha256/phash/dhash/whash + 宽高 + cos_key) / `dup_clusters`。
- `collections`/`collection_works`(主题展) / `ingest_batches`。
- `mu_*`(museum 用户/事件/评论/评分/收藏/人设/口味/生成；**注意 work 键是文本,与 bigint work_id 不同源,需映射**)。
- **不在库里(仍是策展 lore JSON)**：艺术史"力"关系(kg-forces/dynamics/context/lineage/drift)、谱系边——**这些保持人工策展,不强行从管线生成**。

## 2. 知识结构页 · 打通清单（按数据就绪度 + 价值排序）
活库已能直接喂的（schema 同构/字段齐）：

| 优先 | 页面 | 需要的数据 | 库里有? | 投影方式 |
|---|---|---|---|---|
| ★1 | **kg-artworks**(标注画廊) | V2 六维 | ✅ 完全同构(就是闸门产出) | 导出 `kg_artwork_v2_live.json`(kept) 或直接 /cat/ |
| ★2 | **kg-affect**(情绪VAD点云) | vad/anchor/channels | ✅ | 导出 affect 切片 |
| ★3 | **kg-worldview-map / kg-galaxy** | wv/x/y + style + 关系 | ✅ wv/x/y(worldview过闸产);关系用真源谱系(暂无→用style聚类) | 导出 worldview 点云 |
| ★4 | **kg-style-vectors/3d/stats/compare** | language7 数值指纹 | ✅ | 导出 language 向量 |
| ★5 | **kg-subject / kg-subject-map** | subject_tags/objects | ✅ | 导出题材索引 |
| ★6 | **kg-artist* / roster / atlas** | 艺术家 + 其作品聚合 | ✅(元数据部分缺) | 导出 artist 聚合 |
| — | kg-forces/dynamics/context/lineage/drift | 艺术史关系 lore | ❌ 不在管线 | **保持策展 JSON,不动** |
| — | kg-me/taste/foryou/duet | 用户向量 | △ mu_taste 部分 | 后期接 mu_* |
| — | kg-compile(意图编译器) | 生成 | 独立子系统 | 单独规划 |

消费页：museum/gallery/wander/concept/variant → 同理,**新建 live 版**读投影；art.html 已接 /cat/exhibit(对外面已落地)。

## 3. 投影层设计（打通的机械）
**`pipeline/scripts/build_projections.py`**（新建）：一个脚本把活库导成各页要的 JSON 切片,输出到 `web/data/live/`(新目录,不覆盖旧 demo):
- `artworks_v2.json`(kept 的完整 V2) · `affect.json`(VAD点云) · `worldview.json`(wv/x/y点云) · `language_vectors.json`(7维) · `subjects.json`(题材→作品) · `artists.json`(艺术家聚合) · `styles.json`(32风格)。
- 作用域默认 **kept(核心资产)** 或 **exhibited**,避免把 pending/低质灌进知识页。
- 幂等可重跑;过闸推进后重跑即刷新。
- 图片 URL 用 COS + 数据万象缩略图。
**+ 已有 `/cat/` API**：浏览/详情/搜索走 API(分页);全量分析页走导出切片(一次 fetch)。两者并存。

## 4. 后台建设规划（收成 7 模块）
现状 4 模块 → 目标 7：

| 模块 | 管什么 | 现状 → 要补 |
|---|---|---|
| **1 数据进料** | 导入/来源/COS/清洗去重 | ✅COS+异常雷达 → 补:去重控件(跑xdedup/阈值)、补图重灌入口 |
| **2 标注开闸** | gate队列/进度/抽检纠错 | ✅ → 补:err重试一键、按来源队列 |
| **3 标准与词表** | styles/worldview/subject/质量rubric/**提示词** | ⚠️只读 → **升级为可在线编辑**(改即生效) |
| **4 艺术家·元数据** | artists/alias/生卒 | ✅基础 → 补:别名合并、缺口补全 |
| **5 策展与展出** | exhibited/collections | ✅ → 补:主题展组卷(往展里加作品) |
| **6 知识结构投影** | 一键重投影 + 各 live 页状态 | ❌新建:跑 build_projections、看各页数据新鲜度、跳转预览 |
| **7 运营** | 用户互动(mu_*评论审核)/生成/系统运维 | ✅基础 → 补:评论审核、服务状态、mu_键映射 |

## 5. 分期路线图
- **第一期(打通,最高价值)**：建 `build_projections.py` → 导出 live 切片 → **copy kg-artworks→kg-artworks-live 接活数据**(样板,schema一致最快) → 后台加 **模块6 投影**(一键重投影+预览)。验证"库→投影→知识页"闭环跑通。
- **第二期(铺开知识页)**：affect/worldview/galaxy/style/subject/artist 逐个出 live 版(都 copy 旧页改数据源,旧页不动)。
- **第三期(后台补全)**：模块3 标准可编辑 + 模块4 艺术家补全 + 模块5 组卷 + 模块7 运营。
- **贯穿**：worldview 过闸继续积累(投影质量随数据涨);旧 demo 页全程保留。

## 6. 落地约定
- live 页 = 旧页 copy 后只换数据源(`fetch demo.json` → `fetch data/live/*.json` 或 `/cat/`),保留旧页 URL 不变。
- 新页一律登记进 `home.html` 首页索引(按既定规矩),标"对内/对外/活数据"。
- 投影脚本、live 数据目录纳入 git;旧 demo JSON 不动。
