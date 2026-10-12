#!/bin/bash
# R-Music 新前端上线：零停机替换 dist 内容
# 关键点：dist 是 docker 的目录绑定挂载，直接 mv 会让容器继续看旧 inode，
#        所以只清空并覆盖内容，保持 dist 目录本身不变，nginx 立刻生效、无需重建容器。
set -euo pipefail
cd /data/sunboss/music
TAR=${1:-/tmp/r-music-dist.tar.gz}
[ -f "$TAR" ] || { echo "找不到 $TAR"; exit 1; }
TS=$(date +%Y%m%d-%H%M%S)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
tar -xzf "$TAR" -C "$STAGE"
[ -f "$STAGE/index.html" ] || { echo "包内没有 index.html，拒绝上线"; exit 1; }

cp -a dist "dist.bak.$TS"          # 备份当前前端（可一键回滚）
find dist -mindepth 1 -delete      # 清空内容但保留 dist 目录本身
cp -a "$STAGE"/. dist/             # 换上新构建
echo "$TS" > .last_deploy
echo "已上线 $TS：$(find dist -type f | wc -l) 个文件 / $(du -sh dist | cut -f1)"
echo "保留的备份：$(ls -d dist.bak.* | tail -3 | tr '\n' ' ')"
