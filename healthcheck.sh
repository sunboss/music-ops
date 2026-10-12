#!/usr/bin/env bash
# R-Music 线上健康巡检（在东京服务器上运行）
# 退出码 0 = 全绿；非 0 = 有故障（供 systemd timer / 外部告警判断）
set -u

DIR=/data/sunboss/music
LOG="$DIR/data/health.log"
FAIL=0

ok()  { echo "  ✔ $*"; }
bad() { echo "  ✘ $*"; FAIL=1; }

run_checks() {
  echo "===== $(date '+%F %T %Z') ====="

  # 1. 容器
  for c in music-web music-enhancer music-api music-go-adapter; do
    if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]; then
      ok "容器 $c 运行中"
    else
      bad "容器 $c 未运行"
    fi
  done

  # 2. 国内取链通路的两个服务
  if systemctl is-active --quiet music-cn-adapter-tunnel; then
    ok "东京端口转发(隧道) 正常"
  else
    bad "东京端口转发 music-cn-adapter-tunnel 挂了 → 换源将全部失效"
  fi
  if systemctl is-active --quiet music-cn-relay; then
    ok "旧 SOCKS 中转 正常（备用）"
  else
    echo "  ⚠ 旧 SOCKS 中转 music-cn-relay 未运行（仅备用通道，不影响主流程）"
  fi

  # 3. 国内适配器本体
  if ssh -o BatchMode=yes -o ConnectTimeout=10 root@111.228.4.117 \
       "systemctl is-active --quiet r-music-adapter" 2>/dev/null; then
    ok "国内换源适配器 正常"
  else
    bad "国内换源适配器 不可用 → 换源将全部失效"
  fi

  # 4. 取链实测（经隧道打国内适配器）
  RES=$(curl -s --max-time 45 \
    "http://172.19.0.1:18811/resolve-url?name=%E6%99%B4%E5%A4%A9&artist=%E5%91%A8%E6%9D%B0%E4%BC%A6&album=&duration=269&source=kuwo" 2>/dev/null)
  if echo "$RES" | grep -q '"url"'; then
    ok "换源取链 正常"
  else
    bad "换源取链 失败：$(echo "$RES" | head -c 90)"
  fi

  # 5. AI 通道（3001 只在容器网络内，必须 docker exec；容器无 curl，用 python）
  VER=$(docker exec music-enhancer python -c "
import json,urllib.request
try:
    d=json.loads(urllib.request.urlopen('http://127.0.0.1:3001/api/version',timeout=20).read())
    print('%s|%s' % (d.get('ai'), d.get('ai_model') or '-'))
except Exception as e:
    print('ERR|' + str(e)[:70])
" 2>/dev/null)
  if [ "${VER%%|*}" = "True" ]; then
    ok "AI 通道 正常（模型 ${VER##*|}）"
  else
    bad "AI 通道异常：$VER"
  fi

  # 6. 播放取源实测
  PLAY=$(docker exec music-enhancer python -c "
import json,urllib.request
try:
    d=json.loads(urllib.request.urlopen('http://127.0.0.1:3001/api/song/url?id=4872687',timeout=120).read())
    it=(d.get('data') or [{}])[0]
    print('src=%s size=%s' % (it.get('source'), it.get('size')))
except Exception as e:
    print('ERR ' + str(e)[:70])
" 2>/dev/null)
  if echo "$PLAY" | grep -q 'src='; then
    ok "播放取源 正常（$PLAY）"
  else
    bad "播放取源 失败：$PLAY"
  fi

  # 7. 磁盘与缓存
  USED=$(df --output=pcent / | tail -1 | tr -dc '0-9')
  FREE=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  if [ "${FREE:-0}" -lt 5 ]; then
    bad "磁盘剩余仅 ${FREE}G，需要清理"
  elif [ "${USED:-0}" -ge 90 ]; then
    bad "磁盘使用率 ${USED}%，偏高"
  else
    ok "磁盘 ${USED}%（剩 ${FREE}G）"
  fi
  ok "音频缓存 $(ls "$DIR/data/audio_cache" 2>/dev/null | wc -l) 首 / $(du -sh "$DIR/data/audio_cache" 2>/dev/null | cut -f1)"

  # 8. 音频缓存 LRU 清理：>6GB 时按修改时间删最旧，回收到 4.5GB 以下
  CACHE_BYTES=$(du -sb "$DIR/data/audio_cache" 2>/dev/null | cut -f1)
  if [ "${CACHE_BYTES:-0}" -gt 6442450944 ]; then
    REMOVED=$(cd "$DIR/data/audio_cache" && ls -tr | head -200 | xargs -r rm -f && echo done)
    ok "LRU 清理已执行：缓存曾超 6GB，已删最旧 200 首（现 $(du -sh "$DIR/data/audio_cache" | cut -f1)）"
  else
    ok "缓存水位正常（$((CACHE_BYTES / 1073741824))GB / 6GB）"
  fi

  # 9. 每日摘要：日期变化时把当次结果存为 data/daily_summary.txt（供推读/告警）
  TODAY=$(date +%F)
  if [ ! -f "$DIR/data/.summary_day" ] || [ "$(cat "$DIR/data/.summary_day")" != "$TODAY" ]; then
    echo "$TODAY" > "$DIR/data/.summary_day"
    cp "$TMPOUT" "$DIR/data/daily_summary.txt" 2>/dev/null || true
  fi

  if [ "$FAIL" -eq 0 ]; then
    echo "结论: 全部正常"
  else
    echo "结论: 存在故障（见上面的 ✘）"
  fi
}

# 注意：不能写成 `run_checks | tee`——管道会让函数在子 shell 里跑，
# 函数内设置的 FAIL 传不出来，脚本就会在检测到故障时仍然返回 0。
TMPOUT=$(mktemp)
run_checks > "$TMPOUT" 2>&1
cat "$TMPOUT" | tee -a "$LOG"
rm -f "$TMPOUT"

# 日志只留最近 2000 行
tail -n 2000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"

exit "$FAIL"
