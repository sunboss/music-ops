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
echo "③ 接下来在 Music Assistant 里（MA 在 HAOS 容器里，路径是容器内部路径！）"
cat <<'TIP'
   路线 A（推荐，最稳）：把曲库放进 HA 的 media 目录，然后
     MA → 设置 → 添加音乐源 → Filesystem (local disk) → 路径填 /media/R-Music
     （容器里能看到的是 HA 的 /media 与 /share，看不到本机 ~/Music）
   路线 B（最快，2 分钟）：本机开文件共享，然后
     MA → 设置 → 添加音乐源 → Filesystem (remote share) → smb://<本机IP>/R-Music
     （macOS：系统设置 → 通用 → 共享 → 文件共享 → 添加本目录，只读即可）
   注意：mp3/flac 标签已写入文件，MA/Plex/Jellyfin 都能正确认歌；不要用 symlink 共享，
     部分 SMB 实现不会跟随软链接。
TIP
