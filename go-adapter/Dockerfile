# R-Music Go 换源适配器（私有 sidecar，不对公网暴露端口）
FROM alpine:3.21

# Go 二进制是 CGO_ENABLED=0 静态编译；TLS 需要 CA 证书，时区需要 tzdata
RUN apk add --no-cache ca-certificates tzdata && rm -rf /var/cache/apk/*

ENV TZ=Asia/Tokyo

WORKDIR /app

# 只拷贝预编译的静态二进制，不在服务器上编源码（服务器无 Go 工具链）
COPY adapter-linux-amd64 /app/adapter
RUN chmod +x /app/adapter && mkdir -p /data

EXPOSE 8811

# 仅监听容器内网；容器不发布端口，只有同一 docker 网络内的 enhancer 能访问
CMD ["/app/adapter", "-addr", "0.0.0.0:8811"]
