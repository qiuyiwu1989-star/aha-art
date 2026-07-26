#!/bin/bash
# ════════════════════════════════════════════════════════════════════
#  造物云 DAM · 统一入库管线 (ingest pipeline)
#  每张新图都经过同一条流水线:抓取 → 去重 → 存COS → 分类 → 主色 → CLIP向量。
#  全程幂等,可重复跑;每天 cron 定时跑,也可手动补跑。
#  设计原则:任何一步只处理"还没做过"的图(增量),所以重复跑很便宜。
# ════════════════════════════════════════════════════════════════════
set -uo pipefail
cd "$(dirname "$0")"
LOG=../logs
mkdir -p "$LOG"
ts(){ date '+%F %T'; }
step(){ echo "[$(ts)] → $1"; }

echo "[$(ts)] ===== 入库管线开始 ====="

# 1) 抓取:造物云「创意设计」团队最近 N 天新执行 → 去重(sha256/phash) → 存COS → 写库(gen_run/gen_file)
step "1/5 抓取+去重+存储 (sync_zwy_daily)"
python3 sync_zwy_daily.py --days "${DAYS:-3}" --workers 6 >> "$LOG/sync_daily.log" 2>&1

# 2) 分类:按 workflow_name + prompt 规则给图打 category(幂等,规则可演进后重跑全量)
step "2/5 分类 (classify_gen)"
python3 classify_gen.py >> "$LOG/classify_gen.log" 2>&1

# 3) 主色:COS 服务端 ?imageAve 算平均色+色相(免下载),只补 hue 为空的
step "3/5 主色 生成区 (gen_color)"
python3 gen_color.py >> "$LOG/gen_color.log" 2>&1
step "3/5 主色 素材库 (zwy_color)"
python3 zwy_color.py >> "$LOG/zwy_color.log" 2>&1
python3 dam_color.py >> "$LOG/dam_color.log" 2>&1   # 艺术库等 cos 库补主色(增量)

# 4) CLIP 向量:ViT-B/32 编码,供语义搜/以图搜图/找同色,只补没向量的
step "4/5 CLIP向量 生成区 (compute_clip)"
python3 compute_clip.py --workers 8 >> "$LOG/compute_clip.log" 2>&1
step "4/5 CLIP向量 素材库 (compute_clip_media)"
python3 compute_clip_media.py --workers 8 >> "$LOG/compute_clip_media.log" 2>&1

# 4.5) AI 自动打标:本地 CLIP 零样本(零token),复用上一步的向量,只标没标过的(增量)
step "4.5 AI自动打标 (auto_tag)"
python3 auto_tag.py --lib both >> "$LOG/auto_tag.log" 2>&1                         # gen+media(老表)
python3 auto_tag.py --lib artwork,guohua,nianhua,infmonkeys >> "$LOG/auto_tag.log" 2>&1  # 新视觉库(统一表,增量)

# 4.6) 近重复聚簇(pHash 汉明):标 dupe_cluster/dupe_rep,折叠近重复用。全量重算(~2min)。
step "4.6 近重复聚簇 (dedup_cluster)"
python3 dedup_cluster.py >> "$LOG/dedup_cluster.log" 2>&1

# 5) 质检/达标:gen_gate prefilter 阶段一(便宜,无VLM)=拉普拉斯测糊 + 纯色/全黑测失败,
#    明显废图 → q_status=rejected,其余 → kept。只处理 pending(增量)。永不物理删。
step "5/5 质检 (gen_gate prefilter)"
python3 gen_gate.py prefilter --workers 16 >> "$LOG/gen_gate.log" 2>&1

# 6) 同步统一向量底座:把新增的生成区/素材库图+向量并入 dam_asset/dam_embedding(幂等 ON CONFLICT)。
#    新库(年画等 COS 扫描)由各自 scan_cos_lib.py 单独入库,不在此处。
step "6 同步统一向量底座 (sync_dam_asset)"
PGPASSWORD=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.aha_pg.json')))['password'])") \
  psql -h 127.0.0.1 -U aha_app -d aha -f sync_dam_asset.sql >> "$LOG/sync_dam_asset.log" 2>&1

echo "[$(ts)] ===== 入库管线完成 ====="
