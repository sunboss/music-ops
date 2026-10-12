#!/usr/bin/env bash
# 对比：同花顺取链耗时（国内机本地 vs 东京经隧道）
URL_Q="name=%E5%90%8C%E8%8A%B1%E9%A1%BA&artist=%E6%9E%97%E5%80%9B%E7%8E%89&album=&duration=237&sources=kuwo,jamendo"

echo -n "  国内机本地(容器外)  : "
S=$(date +%s%N)
ssh -o BatchMode=yes -o ConnectTimeout=10 root@111.228.4.117 \
  "curl -s -o /dev/null --max-time 60 'http://127.0.0.1:8811/resolve-best?$URL_Q'"
echo "$(( ($(date +%s%N)-S)/1000000 )) 毫秒  (含 SSH 往返)"

echo -n "  国内机本地(机上自测): "
ssh -o BatchMode=yes -o ConnectTimeout=10 root@111.228.4.117 \
  'S=$(date +%s%N); curl -s -o /dev/null --max-time 60 "http://127.0.0.1:8811/resolve-best?name=%E5%90%8C%E8%8A%B1%E9%A1%BA&artist=%E6%9E%97%E5%80%9B%E7%8E%89&album=&duration=237&sources=kuwo,jamendo"; echo $(( ($(date +%s%N)-S)/1000000 )) 毫秒'

echo -n "  东京容器经隧道     : "
docker exec music-enhancer python -c "
import time,json,urllib.request
t=time.time()
r=json.loads(urllib.request.urlopen('http://172.19.0.1:18811/resolve-best?name=%E5%90%8C%E8%8A%B1%E9%A1%BA&artist=%E6%9E%97%E5%80%9B%E7%8E%89&album=&duration=237&sources=kuwo,jamendo',timeout=60).read())
print('%.0f 毫秒' % ((time.time()-t)*1000))
"

echo
echo "=== debug 接口返回内容（公网可访问）"
curl -s --max-time 30 "https://music.1234r.com/api/debug/song?id=186016" | head -c 400
echo
