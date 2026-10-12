#!/bin/bash
# 逐平台实测音源可用性（并发，避免一个挂掉的平台拖垮整体）
# 输出 TSV：歌名 歌手 平台 状态 耗时s 直链? 体积MB 说明
set -uo pipefail
ADAPTER="${1:-http://172.19.0.1:18811}"
SRC_LIST="${2:-kuwo kugou qq migu qianqian soda bilibili joox jamendo fivesing netease}"
OUT="${3:-/tmp/src_matrix.tsv}"
TMP=$(mktemp -d)
: > "$OUT"

SONGS=(
  "晴天|周杰伦|269"
  "富士山下|陈奕迅|259"
  "孤勇者|陈奕迅|255"
  "我看|刘弈画|273"
  "Shape of You|Ed Sheeran|233"
)

one() {
  local name="$1" artist="$2" dur="$3" src="$4"
  local nq aq q t0 t1 json status
  nq=$(printf %s "$name" | jq -sRr @uri); aq=$(printf %s "$artist" | jq -sRr @uri)
  # ① 搜索+匹配（单平台）
  t0=$(date +%s.%N)
  json=$(curl -s -m 40 "$ADAPTER/resolve?name=$nq&artist=$aq&duration=$dur&sources=$src")
  t1=$(date +%s.%N)
  status=$(printf %s "$json" | jq -r '.outcomes[0].status // "无响应"' 2>/dev/null || echo "无响应")
  local err hint
  hint=$(printf %s "$json" | jq -r '.outcomes[0].error // ""' 2>/dev/null | head -c 40)
  local cost; cost=$(echo "$t1 - $t0" | bc 2>/dev/null || echo 0)

  local url="" size_mb="-"
  if [ "$status" = "matched" ]; then
    # ② 取真直链并量体积（只对匹配上的做，避免浪费）
    url=$(curl -s -m 40 "$ADAPTER/resolve-best?name=$nq&artist=$aq&duration=$dur&sources=$src" | jq -r '.url // ""' 2>/dev/null)
    if [ -n "$url" ]; then
      local bytes
      bytes=$(curl -s -m 25 -r 0-1 -o /dev/null -D - "$url" 2>/dev/null | awk -F'/' '/[Cc]ontent-[Rr]ange/{gsub(/\r/,"");print $2}' | tail -1)
      [ -z "$bytes" ] && bytes=$(curl -s -m 25 -o /dev/null -w '%{size_download}' -r 0-0 "$url" 2>/dev/null)
      [ -n "$bytes" ] && [ "$bytes" -gt 0 ] 2>/dev/null && size_mb=$(echo "scale=1; $bytes/1048576" | bc)
    fi
  fi
  printf '%s\t%s\t%s\t%s\t%.1f\t%s\t%s\t%s\n' "$name" "$artist" "$src" "$status" "$cost" \
    "$([ -n "$url" ] && echo 是 || echo 否)" "$size_mb" "$hint" >> "$TMP/$src.part"
}

export -f one
export ADAPTER

for s in "${SONGS[@]}"; do
  IFS='|' read -r n a d <<< "$s"
  for p in $SRC_LIST; do
    echo "$n|$a|$d|$p"
  done
done | xargs -P 12 -I{} bash -c 'IFS="|" read -r n a d p <<< "{}"; one "$n" "$a" "$d" "$p"'

cat "$TMP"/*.part > "$OUT" 2>/dev/null
rm -rf "$TMP"
echo "=== 明细写入 $OUT（$(wc -l < "$OUT") 行）"
sort -t$'\t' -k3,3 "$OUT" | awk -F'\t' '{printf "  %-11s %-8s %-16s %5ss  直链=%s %sMB %s\n", $3, $1, $4, $5, $6, $7, $8}'
