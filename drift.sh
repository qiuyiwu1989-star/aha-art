#!/usr/bin/env bash
# drift.sh · 只读漂移体检 —— 看 web/ 仓库源 与 线上部署目录 的分叉情况。
# 不改任何文件。用于「退役 demo / 收敛单一源」的持续跟踪(见 仓库关系与退役计划.md)。
# 用法:  bash drift.sh          # 概览
#         bash drift.sh -v       # 列出每个分叉/缺失文件
set -euo pipefail
WEB="$(cd "$(dirname "$0")/web" && pwd)"
PUB="${AHA_PUB:-/data/pub/p/aha}"
verbose="${1:-}"
match=0; webmiss=0; pubmiss=0; diverge=0; total=0
miss=(); div=(); only=()
# 线上 → 仓库
for d in "$PUB"/*.html; do
  f=$(basename "$d"); total=$((total+1)); w="$WEB/$f"
  if [ ! -f "$w" ]; then webmiss=$((webmiss+1)); miss+=("$f")
  elif diff -q "$d" "$w" >/dev/null 2>&1; then match=$((match+1))
  else diverge=$((diverge+1)); div+=("$f"); fi
done
# 仓库有、线上没有(仓库独有,未部署)
for w in "$WEB"/*.html; do
  f=$(basename "$w"); [ -f "$PUB/$f" ] || { pubmiss=$((pubmiss+1)); only+=("$f"); }
done
echo "═══ aha 漂移体检 ($(date +%F\ %H:%M)) ═══"
echo "线上 $total 页:  ✓一致 $match   ⚠分叉 $diverge   ⊘仓库缺 $webmiss   ↑仓库独有(未部署) $pubmiss"
if [ "$verbose" = "-v" ]; then
  [ ${#div[@]}  -gt 0 ] && printf '\n⚠ 分叉(线上≠仓库,需人工定哪版为准):\n' && printf '   %s\n' "${div[@]}"
  [ ${#miss[@]} -gt 0 ] && printf '\n⊘ 仓库缺(线上有、git 无 → 抢救:cp %s/X web/X):\n' "$PUB" && printf '   %s\n' "${miss[@]}"
  [ ${#only[@]} -gt 0 ] && printf '\n↑ 仓库独有(改了没部署 → cp web/X %s/):\n' "$PUB" && printf '   %s\n' "${only[@]}"
fi
echo
echo "目标:分叉=0 且 仓库缺=0 → 仓库即单一源,可退役 aha-art-demo(见 仓库关系与退役计划.md)"
