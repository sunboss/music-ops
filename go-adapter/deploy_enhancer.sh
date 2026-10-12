#!/bin/bash
# 安全上线 enhancer（服务端 Python）：
#   1. 本地静态检查（pyflakes 抓未定义名字 + 语法编译）—— 今天就是因为漏了这步把线上打挂过
#   2. 服务器端备份当前文件
#   3. 上传 + 重启
#   4. 健康检查（进程稳定 + 关键接口 2xx），不过就自动回滚
set -euo pipefail
cd "$(dirname "$0")/.."
SRV=${SRV:-/data/sunboss/music}
HOST=${HOST:-root@64.83.34.204}

echo "① 本地静态检查"
python3 -m pyflakes ai_service/server.py || { echo "  ✗ pyflakes 发现问题，拒绝上线"; exit 1; }
python3 -m py_compile ai_service/server.py || { echo "  ✗ 语法编译失败，拒绝上线"; exit 1; }
echo "  ✓ pyflakes 与编译均通过"

TS=$(date +%Y%m%d-%H%M%S)
echo "② 备份服务器现有文件"
ssh -o ConnectTimeout=20 "$HOST" "cp $SRV/ai_service/server.py $SRV/ai_service/server.py.bak-$TS && echo  server.py.bak-$TS"

echo "③ 上传并重启"
scp -q ai_service/server.py "$HOST:$SRV/ai_service/server.py"
ssh -o ConnectTimeout=20 "$HOST" "cd $SRV && docker compose restart enhancer >/dev/null 2>&1"
# 等就绪要轮询，不能靠固定 sleep：绑定端口可能比 9 秒慢，固定等待会把成功部署误判成失败并回滚
for i in $(seq 1 30); do
  if ssh -o ConnectTimeout=15 "$HOST" "docker exec music-enhancer python3 -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:3001/health',timeout=3)\"" >/dev/null 2>&1; then
    echo "  就绪（等了 $((i*2))s）"
    break
  fi
  sleep 2
  [ "$i" = "30" ] && echo "  ✗ 60 秒内未就绪"
done
ssh -o ConnectTimeout=20 "$HOST" "docker ps --format '{{.Names}} {{.Status}}' | grep enhancer"

echo "④ 健康检查（容器重启后边缘会有几秒空窗，每个端点重试 3 次再判失败）"
ok=1
probe() {   # $1=方法 $2=路径；回显状态码
  local m="$1" ep="$2" code=""
  for try in 1 2 3; do
    if [ "$m" = "HEAD" ]; then
      code=$(curl -s -o /dev/null -m 45 -I -w "%{http_code}" "https://music.1234r.com$ep" || echo 000)
    else
      code=$(curl -s -o /dev/null -m 45 -w "%{http_code}" "https://music.1234r.com$ep" || echo 000)
    fi
    case "$code" in 2*) break ;; esac
    sleep 5
  done
  echo "$code"
}
for ep in "/api/version" "/api/personal_fm" "/api/audio/proxy?id=186016" "/api/ma/resolve?id=186016"; do
  code=$(probe GET "$ep")
  echo "  $ep -> $code"
  case "$code" in 2*) : ;; *) ok=0 ;; esac
done
hcode=$(probe HEAD "/api/audio/proxy?id=186016")
echo "  HEAD /api/audio/proxy -> $hcode"
[ "$hcode" = "200" ] || ok=0

if [ "$ok" != "1" ]; then
  echo "✗ 健康检查未通过，自动回滚到 server.py.bak-$TS"
  ssh -o ConnectTimeout=20 "$HOST" "cd $SRV && cp ai_service/server.py.bak-$TS ai_service/server.py && docker compose restart enhancer >/dev/null 2>&1; sleep 8; docker ps --format '{{.Names}} {{.Status}}' | grep enhancer"
  exit 1
fi
echo "✓ 上线完成 ($TS)"
