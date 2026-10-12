#!/bin/bash
# 一键回滚前端：不传参则回到最近一次备份
set -euo pipefail
cd /data/sunboss/music
B=${1:-$(ls -d dist.bak.* 2>/dev/null | sort | tail -1)}
[ -n "$B" ] && [ -d "$B" ] || { echo "找不到备份目录"; ls -d dist.bak.* 2>/dev/null; exit 1; }
find dist -mindepth 1 -delete
cp -a "$B"/. dist/
echo "已回滚到 $B：$(find dist -type f | wc -l) 个文件"
