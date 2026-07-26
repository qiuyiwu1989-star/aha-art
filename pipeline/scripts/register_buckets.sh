#!/bin/bash
cd "$(dirname "$0")"
ts(){ date '+%F %T'; }
for spec in "opendesign-1254041526|opendesign|opendesign-bucket" "yishujia-1254041526|ysj|ysj-bucket" "zhongtai-1254041526|zhongtai|zhongtai-bucket"; do
  IFS='|' read -r bk lib src <<< "$spec"
  echo "[$(ts)] 登记 $bk → lib=$lib"
  python3 scan_cos_lib.py --bucket "$bk" --prefix "" --lib "$lib" --source "$src" --register-only
done
echo "[$(ts)] 三桶登记完成"
