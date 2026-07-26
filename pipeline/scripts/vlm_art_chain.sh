#!/bin/bash
# 顺序给其余艺术库 VLM 鉴赏标注(增量可续)。artwork 17万最大,排最后。
cd "$(dirname "$0")"
for lib in yishujia beitie artwork; do
  echo "[$(date '+%F %T')] ===== $lib 开始 ====="
  python3 vlm_art.py --lib "$lib" --workers 4 >> "../logs/vlm_art_${lib}.log" 2>&1
  echo "[$(date '+%F %T')] ===== $lib 完成 ====="
done
