#!/bin/bash
cd "$(dirname "$0")"
ts(){ date '+%F %T'; }
echo "[$(ts)] === 编码队列(workers=6) ==="
for lib in infmonkeys artwork guohua; do
  echo "[$(ts)] >>> $lib"
  python3 scan_cos_lib.py --lib "$lib" --encode-only --workers 6
  echo "[$(ts)] <<< $lib 完成"
done
echo "[$(ts)] === 全部完成 ==="
