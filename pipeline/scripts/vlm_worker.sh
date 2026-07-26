#!/bin/bash
# DAM VLM 标注常驻 worker(单 MIMO 流,顺序处理,全部增量幂等,处理完就 sleep 空转)。
# 由 systemd dam-vlm.service 拉起,活过轮次/重启,断点续。
cd /home/ubuntu/users/qiuyiwu/aha-art/pipeline/scripts
LOG=../logs
while true; do
  python3 vlm_art.py --lib guohua   --workers 6 >> "$LOG/vlm_art_guohua.log"   2>&1   # 5k 国画(高价值先)
  python3 vlm_art.py --lib beitie   --workers 6 >> "$LOG/vlm_art_beitie.log"   2>&1   # 39k 碑帖
  python3 vlm_art.py --lib yishujia  --workers 6 >> "$LOG/vlm_art_yishujia.log" 2>&1   # 31k 艺术数据集
  python3 vlm_art.py --lib webdesign  --workers 6 >> "$LOG/vlm_art_webdesign.log"  2>&1  # 11k 网页设计(原零标注)
  python3 vlm_art.py --lib media      --workers 6 >> "$LOG/vlm_art_media.log"      2>&1  # 13k 素材库(补细描述)
  python3 vlm_art.py --lib infmonkeys --workers 6 >> "$LOG/vlm_art_infmonkeys.log" 2>&1  # 44k Artist1.0(补细描述)
  python3 vlm_art.py --lib artwork    --workers 6 >> "$LOG/vlm_art_artwork.log"    2>&1  # 17万 油画(路径无元数据,VLM是唯一可搜信息,优先)
  python3 gen_gate.py vlm --source zaowuyun_team --workers 6 >> "$LOG/gen_gate_vlm.log" 2>&1  # 10万 生成质检(gen已有prompt/标签,垫底)
  python3 normalize_moods.py >> "$LOG/normalize_moods.log" 2>&1
  python3 build_text.py >> "$LOG/build_text.log" 2>&1
  sleep 600
done
