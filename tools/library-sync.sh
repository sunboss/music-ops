#!/bin/bash
# 把东京服务器上的「带标签曲库」同步到本机（供 Music Assistant / Plex / Jellyfin 索引）
#
# 为什么是"拉"而不是"推"：本机有到服务器的 SSH 密钥，服务器没有到本机的密钥；
# 而且不需要把 SMB/NFS 暴露到公网（445/2049 是被扫描最凶的端口）。
#
# 用法：
#   bash tools/library-sync.sh                 # 默认同步到 ~/Music/R-Music
#   TARGET=/path/to/folder bash tools/library-sync.sh
#   HOST=root@64.83.34.204 SRC=/data/sunboss/music/data/library bash tools/library-sync.sh
set -euo pipefail
HOST="${HOST:-root@64.83.34.204}"
SRC="${SRC:-/data/sunboss/music/data/library}"
TARGET="${TARGET:-$HOME/Music/R-Music}"

mkdir -p "$TARGET"
echo "① 从 $HOST:$SRC 同步到 $TARGET"
# --delete：服务器上被淘汰的曲目在本机也清掉，保持镜像一致
# 注意：macOS 自带的是老版 rsync(2.6.9)，不支持 --info=stats2，用 --stats
rsync -a --delete --partial --stats \
      -e "ssh -o ConnectTimeout=20" "$HOST:$SRC/" "$TARGET/"

echo "② 结果"
n=$(find "$TARGET" -maxdepth 1 -type f \( -name '*.mp3' -o -name '*.flac' -o -name '*.m4a' -o -name '*.ogg' -o -name '*.wav' \) | wc -l | tr -d ' ')
echo "   曲目 $n 首，合计 $(du -sh "$TARGET" | cut -f1)"
echo "   播放清单：$TARGET/library.m3u8 $( [ -f "$TARGET/library.m3u8" ] && echo '(存在)' || echo '(缺失)' )"
echo
echo "③ 接下来在 Music Assistant 里：设置 → 添加音乐提供方 → Filesystem（本地/网络文件夹）"
echo "   路径填：$TARGET"
echo "   若 MA 跑在另一台机器（如 HAOS）上，把上面这个目录共享给它，或在它上面跑同一脚本。"
