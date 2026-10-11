# ==============================================================================
# R-Music: YesPlayMusic + Go-Music-DL + AI Search & Management All-in-One Dockerfile
# ==============================================================================

FROM alpine:3.21

# 安装运行环境: Nginx, Python3 (用于轻量AI服务), FFmpeg, tzdata, supervisor, curl
RUN apk add --no-cache \
    nginx \
    supervisor \
    ffmpeg \
    python3 \
    py3-pip \
    curl \
    tzdata \
    ca-certificates \
    && rm -rf /var/cache/apk/*

ENV TZ=Asia/Tokyo

# 创建应用目录与用户
RUN adduser -D -s /bin/sh appuser \
    && mkdir -p /app /data/music /var/log/supervisor /run/nginx /etc/nginx/conf.d

WORKDIR /app

# 复制 go-music-dl 二进制文件（可由官方镜像提取或预编译）
# 复制 YesPlayMusic 前端静态产物
# 复制 AI 服务脚本与配置文件
COPY docker/ /app/docker/
COPY ai_service/ /app/ai_service/
COPY nginx/ /etc/nginx/conf.d/
COPY supervisord.conf /etc/supervisord.conf

# 权限配置
RUN chown -R appuser:appuser /data/music /app

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
