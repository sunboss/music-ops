#!/usr/bin/env bash
# 构建 Go 换源适配器并部署到线上（本脚本在本机运行）
# 说明：不在服务器上编源码（服务器无 Go 工具链），只上传交叉编译好的静态二进制。
set -euo pipefail

SERVER="${SERVER:-root@64.83.34.204}"
REMOTE_DIR="${REMOTE_DIR:-/data/sunboss/music/go-adapter}"
UPSTREAM_DIR="${UPSTREAM_DIR:-$HOME/Desktop/AI/music-ops/../ai-incubator/go-music-dl}"

echo "== 1. 构建 linux/amd64 静态二进制"
cd "$(dirname "$0")/../go-music-dl-src/upstream"
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o ../../go-adapter/adapter-linux-amd64 ./cmd/phase2-adapter
cd - >/dev/null

echo "== 2. 上传二进制与 Dockerfile"
ssh "$SERVER" "mkdir -p $REMOTE_DIR"
scp go-adapter/adapter-linux-amd64 go-adapter/Dockerfile "$SERVER:$REMOTE_DIR/"

echo "== 3. 上线（在服务器执行）"
ssh "$SERVER" "cd /data/sunboss/music && docker compose up -d --build go-adapter && docker compose ps"

echo "完成。适配器仅监听容器网络，未对公网发布端口。"
