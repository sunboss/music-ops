# R-Music 运维手册（music.1234r.com）

## 架构

```
浏览器 ──► Cloudflare ──► music-web (Nginx)
                            ├── /            静态前端 YesPlayMusic + sub_filter 注入定制主题/脚本
                            └── /api/*       ──► music-enhancer (Python, :3001)
                                                  ├── 官方可用 ──► music-api (netease_cloud_music_api, :3000)
                                                  └── 官方不可用 ──► Go 换源适配器（跑在国内机）
                                                                        └── 严格匹配 → 大模型终审
                                                                              └── 取直链（原生国内出口）
```

- 线上目录：`/data/sunboss/music`（服务器 `64.83.34.204`）
- 容器：`music-web` / `music-enhancer` / `music-go-adapter` / `music-api`
- 换源适配器与网易云 API **都不对外发布端口**，只走内部网络

## ⚠️ 关键依赖：国内取链

**适配器跑在国内机**（`111.228.4.117`，systemd `r-music-adapter.service`，监听 `127.0.0.1:8811`），
东京只做端口转发把它接到 Docker 网段：

```
music-cn-adapter-tunnel.service   # 东京：ssh -N -L 172.19.0.1:18811:127.0.0.1:8811 root@111.228.4.117
```

`enhancer` 用 `GO_ADAPTER=http://172.19.0.1:18811`（主）+
`GO_ADAPTER_FALLBACK=http://go-adapter:8811`（东京本地容器，备用）。

**为什么要放国内**：国内平台的签名直链接口**只对国内 IP 返回真实地址**（东京直连返回 `"None"`）。
早期做法是东京容器经 SOCKS5 代理逐请求出国，链路慢且咪咕一类接口会超时；
把适配器整体放到国内机后是**原生国内出口**，实测取链 0.4 秒，且不再依赖逐请求代理。
**音频字节仍由东京直连下载**（国内机到东京带宽只有 ~19KB/s，绝不能让它中转音频）。

主地址不通时 `go_call()` 会自动回退到备用地址；两个都不通则如实报「无可用音源」，不伪造。

服务一旦挂掉，表现为：所有需要换源的歌都变成「无可用音源」。

```bash
# 国内机（换源适配器本体）
ssh root@64.83.34.204 'ssh root@111.228.4.117 "systemctl status r-music-adapter"'
# 东京（端口转发）
systemctl status music-cn-adapter-tunnel
journalctl -u music-cn-adapter-tunnel -n 30
systemctl status music-cn-relay        # 旧的 SOCKS 中转（备用，可保留）
systemctl restart music-cn-relay       # 重启
ss -lnt | grep 11080                   # 端口监听（绑定 172.19.0.1，仅 Docker 网段可达）
journalctl -u music-cn-relay -n 30     # 日志
```

> 配置代理时必须**同时**设置 `HTTP_PROXY` 与 `HTTPS_PROXY`（取链接口走 HTTPS），
> 只设一个代理不生效。

## 播放质量红线

| 规则 | 位置 | 原因 |
|---|---|---|
| 歌名+版本严格相等 | `go-adapter` 的 `match()` | 防翻唱 / 不同版本混入 |
| 歌手允许写法差异（分隔符、`feat.`、大小写、包含关系） | 同上 | 各平台写法不同，硬判会误杀 |
| **时长必须吻合（±3 秒）** | 同上 | 区分原曲 / 试听片段最可靠的依据 |
| 专辑名**不参与**判定 | 同上 | 各平台专辑名写法差异极大，硬判会误杀大量可播放曲目 |
| 落盘后解码复核真实时长 | `ai_service/server.py` 的 `duration_ok()` | 上游可能给 30 秒试听片段，靠文件本身才能确认 |
| 不符时标记不可播放、**不回流式代理** | 同上 | 宁可显示「无音源」，也不让用户只听到 30 秒 |
| 官方试听片段（`freeTrialInfo` 非空）不回填 | 同上 `strip_trial()` | 否则播放器只能播 30 秒 |
| `size` / `br` 只用实测值，取不到填 0 | 同上 `measure_size()` | 不伪造 |

## 音频播放路径：整曲落盘

`/api/audio/proxy?id=<歌曲id>`

1. 命中 `/data/audio_cache/<id>.<ext>` → 直接本地播放（带 Range，拖动瞬时响应）
2. 未命中 → 解析直链 → **整曲下载落盘** → 校验真实时长 → 本地播放
3. 落盘内容时长不符 / 过小 → 判为试听片段，标记 `__REJECTED__`，返回 404

落盘带来的好处：签名直链中途过期不再影响播放、拖动定位秒开、上游抖动无感。
目录保留最近 400 首（`AUDIO_MAX_FILES`），超出按最近使用时间淘汰。

## 搜索接口

网易云的 `/search` 返回的数据结构已损坏（歌名错乱、缺歌手与时长），
`enhancer` 会自动把 `/api/search` 改写为 `/cloudsearch` —— 字段与前端一致
（`ar` / `al` / `dt` / `fee` / `privilege`）。**不要改回 `/search`。**

## 常用排查

```bash
cd /data/sunboss/music

docker compose ps                                          # 容器状态
docker logs --tail 50 music-enhancer                       # 换源/落盘/拒绝原因
docker logs --tail 30 music-go-adapter                     # 适配器
docker exec music-web nginx -t                             # 配置语法

# 换源是否正常（返回 matched + 真实 http 链接才算正常）
docker exec music-enhancer python -c "
import urllib.request,urllib.parse
q=urllib.parse.urlencode({'name':'晴天','artist':'周杰伦','duration':'269','sources':'kuwo'})
print(urllib.request.urlopen('http://go-adapter:8811/resolve-best?'+q,timeout=60).read().decode()[:300])"

# 落盘目录
docker exec music-enhancer ls -lh /data/audio_cache

# 公网端到端
curl -s "https://music.1234r.com/api/song/url?id=186016" | head -c 300
curl -s -r 0-1023 -o /dev/null -w "Range 状态=%{http_code} 长度=%{size_download}\n" \
     "https://music.1234r.com/api/audio/proxy?id=186016"
```

## 前端定制（零侵入）

全部通过 Nginx `sub_filter` 注入，不改 `dist` 源码：

- `custom/custom-theme.css` — 主题 / 响应式 / 毛玻璃
- `custom/r-music-inject.js` — Logo 注入、Service Worker 清理
- `custom/sw-reset.js` — 覆盖原版 Workbox SW（原版会预缓存旧首页，导致注入失效）

```bash
scp nginx/default.conf root@64.83.34.204:/data/sunboss/music/nginx.conf
ssh root@64.83.34.204 'docker exec music-web nginx -s reload'
```

**Cloudflare 会缓存定制资源约 4 小时**，每次改动前端资源必须递增
`nginx.conf` 里 `sub_filter` 的 `?v=` 版本号（当前 `20261012k`），否则用户看不到更新。

## 备份

`/data/sunboss/music/backup-go-adapter/` 下有接入前的 `nginx.conf`、`docker-compose.yml`、`server.py` 快照。
