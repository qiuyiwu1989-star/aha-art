#!/bin/bash
cd "$(dirname "$0")"
ts(){ date '+%F %T'; }
echo "[$(ts)] === 新库向量编码开始 ==="
for lib in guohua infmonkeys artwork; do
  echo "[$(ts)] >>> 编码 $lib"
  python3 scan_cos_lib.py --lib "$lib" --encode-only --workers 8
  echo "[$(ts)] <<< $lib 完成"
done
echo "[$(ts)] === 全部完成 ==="
