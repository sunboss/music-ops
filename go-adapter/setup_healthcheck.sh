#!/usr/bin/env bash
# 在东京服务器安装巡检：脚本 + systemd 定时器（每 15 分钟）
set -e
mkdir -p /data/sunboss/music/data

cat > /etc/systemd/system/r-music-healthcheck.service <<'EOF'
[Unit]
Description=R-Music 线上健康巡检
After=network-online.target docker.service

[Service]
Type=oneshot
ExecStart=/data/sunboss/music/healthcheck.sh
EOF

cat > /etc/systemd/system/r-music-healthcheck.timer <<'EOF'
[Unit]
Description=R-Music 健康巡检定时器（每 15 分钟）

[Timer]
OnBootSec=3min
OnUnitActiveSec=15min
Unit=r-music-healthcheck.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now r-music-healthcheck.timer >/dev/null 2>&1
chmod +x /data/sunboss/music/healthcheck.sh

echo -n "定时器: "; systemctl is-active r-music-healthcheck.timer
echo -n "下次触发: "; systemctl show r-music-healthcheck.timer -p NextElapseUSecRealtime --value
echo
echo "=== 立即跑一次巡检"
/data/sunboss/music/healthcheck.sh; echo "退出码: $?"
