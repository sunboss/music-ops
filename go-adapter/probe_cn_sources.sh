#!/usr/bin/env bash
# 国内机上逐平台体检：搜索+取链是否可用
for s in kuwo kugou qq migu bilibili qianqian soda fivesing netease jamendo; do
  printf "  %-9s " "$s"
  out=$(curl -s --max-time 60 "http://127.0.0.1:8811/resolve-url?name=%E6%99%B4%E5%A4%A9&artist=%E5%91%A8%E6%9D%B0%E4%BC%A6&album=&duration=269&source=$s")
  if echo "$out" | grep -q '"url"'; then
    echo "✔ $(echo "$out" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' | head -1) | $(echo "$out" | head -c 90 | tail -c 40)"
  else
    echo "✘ $(echo "$out" | head -c 110)"
  fi
done
echo
echo "=== 十首中文歌在 kuwo/kugou/qq 三个源上的覆盖"
i=0; ok=0
while IFS='|' read -r n a d; do
  [ -z "$n" ] && continue
  hit=""
  for s in kuwo kugou qq; do
    o=$(curl -s --max-time 45 --get "http://127.0.0.1:8811/resolve-url" --data-urlencode "name=$n" --data-urlencode "artist=$a" --data-urlencode "album=" --data-urlencode "duration=$d" --data-urlencode "source=$s")
    echo "$o" | grep -q '"url"' && hit="$hit $s"
  done
  i=$((i+1)); [ -n "$hit" ] && ok=$((ok+1))
  printf "  %-22s %-14s 命中:%s\n" "$n" "$a" "${hit:-无}"
done <<'EOF'
晴天|周杰伦|269
十年|陈奕迅|205
富士山下|陈奕迅|259
红豆|王菲|259
光辉岁月|BEYOND|299
孤勇者|陈奕迅|245
消愁|毛不易|271
认真的雪|薛之谦|255
爱在西元前|周杰伦|234
海阔天空|BEYOND|240
EOF
echo "  合计: $ok/$i 首至少有一个源命中"
