#!/usr/bin/env bash
# 在国内服务器安装 R-Music Go 换源适配器（原生国内出口）
set -e

mkdir -p /opt/r-music-adapter
[ -f /opt/r-music-adapter/cookies.json ] || echo '{}' > /opt/r-music-adapter/cookies.json
chmod +x /opt/r-music-adapter/adapter

cat > /etc/systemd/system/r-music-adapter.service <<'EOF'
[Unit]
Description=R-Music Go 换源适配器（国内原生出口）
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/r-music-adapter/adapter -addr 127.0.0.1:8811 -cookies /opt/r-music-adapter/cookies.json
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable r-music-adapter >/dev/null 2>&1 || true
systemctl restart r-music-adapter
sleep 3
echo -n "服务状态: "
systemctl is-active r-music-adapter
echo -n "监听: "
ss -ltn | grep 8811 || echo "未监听"
echo -n "自测(晴天,kuwo): "
curl -s --max-time 40 "http://127.0.0.1:8811/resolve-url?name=%E6%99%B4%E5%A4%A9&artist=%E5%91%A8%E6%9D%B0%E4%BC%A6&album=&duration=269&source=kuwo" | head -c 130
echo
