#!/bin/bash
cd "$(dirname "$0")"
ts(){ date '+%F %T'; }
echo "[$(ts)] === 统一编码队列开始(workers=4 防OOM) ==="
for lib in guohua infmonkeys zhongtai ysj opendesign artwork; do
  echo "[$(ts)] >>> 编码 $lib"
  python3 scan_cos_lib.py --lib "$lib" --encode-only --workers 4
  echo "[$(ts)] <<< $lib 完成"
done
echo "[$(ts)] === 全部库编码完成 ==="
