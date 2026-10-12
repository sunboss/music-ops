#!/usr/bin/env bash
# 在东京服务器上建立到国内机的端口转发：172.19.0.1:18811 -> 国内机 127.0.0.1:8811
# Go 换源适配器跑在国内机（原生国内出口），东京这边只做转发，省掉 SOCKS 代理开销。
set -e
cat > /etc/systemd/system/music-cn-adapter-tunnel.service <<'EOF'
[Unit]
Description=R-Music 国内换源适配器端口转发 (18811 -> 111.228.4.117:8811)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -N -L 172.19.0.1:18811:127.0.0.1:8811 \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/root/.ssh/known_hosts \
  root@111.228.4.117
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable music-cn-adapter-tunnel >/dev/null 2>&1 || true
systemctl restart music-cn-adapter-tunnel
sleep 3
echo -n "隧道状态: "; systemctl is-active music-cn-adapter-tunnel
echo -n "监听: "; ss -ltn | grep 18811 || echo 未监听
echo -n "经隧道取链(晴天): "
curl -s --max-time 45 "http://172.19.0.1:18811/resolve-url?name=%E6%99%B4%E5%A4%A9&artist=%E5%91%A8%E6%9D%B0%E4%BC%A6&album=&duration=269&source=kuwo" | head -c 120
echo
