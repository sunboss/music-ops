#!/usr/bin/env bash
# R-Music 空间清理（只动我们自己的东西，不碰其他服务的镜像/卷）
set -u

echo "===== 清理前 ====="
df -h / | tail -1
docker system df

echo
echo "===== 1) 移除早期实验遗留容器 test-unm ====="
if docker ps -a --format '{{.Names}}' | grep -qx test-unm; then
  docker rm -f test-unm >/dev/null 2>&1 && echo "  已移除 test-unm（unblock 增强服务的早期试验，已被 music-enhancer 取代）"
else
  echo "  没有 test-unm"
fi

echo
echo "===== 2) 移除我们不参与运行的构建产物镜像 ====="
# web 只挂载 ./dist 静态目录，这两个镜像只在早期构建时用过，运行时不依赖
for img in yesplay-build:latest yesplaymusic:latest; do
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -qx "$img"; then
    size=$(docker images --format '{{.Size}}' "$img" | head -1)
    docker rmi "$img" >/dev/null 2>&1 && echo "  已移除 $img ($size)" || echo "  跳过 $img（仍被引用）"
  fi
done

echo
echo "===== 3) 清构建缓存（纯中间产物，安全） ====="
docker builder prune -af 2>&1 | tail -2

echo
echo "===== 4) 清悬空镜像与停止的测试容器 ====="
docker image prune -f 2>&1 | tail -1

echo
echo "===== 清理后 ====="
df -h / | tail -1
docker system df

echo
echo "===== 确认我们的服务未受影响 ====="
for c in music-web music-enhancer music-api music-go-adapter; do
  printf "  %-20s %s\n" "$c" "$(docker inspect -f '{{.State.Status}}' $c 2>/dev/null)"
done
curl -s -o /dev/null -w "  站点首页 HTTP %{http_code}\n" --max-time 20 https://music.1234r.com/
