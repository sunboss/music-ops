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

## 健康巡检与告警

两层，互为补充：

**① 东京本机 systemd 定时器**（每 15 分钟，留本地记录）
```
r-music-healthcheck.timer / .service  →  /data/sunboss/music/healthcheck.sh
日志：/data/sunboss/music/data/health.log（只留最近 2000 行）
```
检查项：三个容器、东京端口转发隧道、国内适配器本体、换源取链实测、
AI 通道、播放取源实测、磁盘水位与缓存量。全绿退出码 0，有故障退出码 1。

**② Hermes cron 看门狗**（每 30 分钟，故障才说话）
```
job: R-Music 线上健康巡检（no_agent + scripts/healthcheck_alert.sh）
```
- 一切正常 → 无输出，完全静默，不会有任何打扰
- 发现故障 → 推送故障摘要 + 排查命令
- 同一故障 2 小时内不重复提醒；恢复时提示一次

> ⚠️ 写这种巡检脚本时注意：**不能用 `run_checks | tee 日志`**——管道会让函数跑在
> 子 shell 里，函数内设置的 `FAIL` 传不出来，脚本就会在检测到故障时仍然返回 0。

## 口味记忆（让 AI 越用越懂你）

前端在**任意 audio 元素**上监听真实收听行为（主播放器和 AI 面板都覆盖），上报给
`/api/client-report` 的 `kind=taste`：

| 行为 | 判定 |
|---|---|
| play | 听满 30 秒**立即记账**，或整曲放完 |
| skip | 听了 3–20 秒就切走 |

服务端存 `taste` 表（含 `song_meta` 缓存歌名/歌手，避免为显示名字去打上游接口），
`taste_context()` 生成一段偏好摘要注入电台/点歌/策展的提示词，例如：
`常听：活着-郝云；偏好歌手：郝云；经常跳过（不要再推荐）：…`

> ⚠️ 别只在切歌/关闭页面时才上报 play——用户一直听下去，这条记录就永远不会落库。
> 听满阈值应立即上报，并用 `reported` 标记避免重复。

## 语音点歌

AI 面板的麦克风按钮走浏览器原生 `SpeechRecognition`（`zh-CN`）：说完直接生成电台。
无该 API 时按钮自动隐藏；未授权时提示「麦克风未授权」。仅在 HTTPS 下可用。

## 容量与自愈

| 机制 | 说明 |
|---|---|
| 音频缓存上限 | 文件数 400 首 + 体积 2GB 双约束，按最近使用时间淘汰 |
| 磁盘水位 | 剩余 < 8G 时缓存收紧到 1/4；启动时先按水位清一次 |
| 无音源主动复核 | 后台每 30 分钟挑最快到期的 3 首重探，平台补上版权就自动恢复显示 |
| 适配器回退 | 国内隧道不通 → 自动回落东京本地容器；都不通 → 如实报「无音源」 |

## AI 能力（大模型直连 DeepSeek 官方）

```
AI_GATEWAY=https://api.deepseek.com/v1     # 直连官方，不经中转网关（网关会按负载对单模型 503）
AI_MODEL=deepseek-chat
AI_MODEL_FALLBACKS=deepseek-reasoner       # 单模型不可用时自动降级
```

密钥只存服务器 `data/ai_key.txt`（600），旧网关密钥备份在 `data/ai_key_gateway.txt`。
容器通过 `AI_API_KEY_FILE` 读取，**不进代码、不进日志、不进仓库**。

大模型承担的是**规则做不到**的四件事：

| 能力 | 位置 | 说明 |
|---|---|---|
| 跨平台候选终审 | `ai_arbitrate` | 把各平台原始候选交给模型判断「是否同一录音同一版本」。规则做不到跨语言/别名：晴天+Jay Chou → 周杰伦 |
| 检索变体生成 | `ai_search_variants` | 歌名带括号补充、歌手写法怪时给出更有效的检索写法 |
| 电台策展 | `ai_curate` | 对**真实可播歌单**取舍排序命名，规则判断不了「像不像这个场景」 |
| 搜索词归属 | `_bg_search_artist` | 搜单首歌名时后台判断「这是谁的歌」，结果缓存 30 天 |

双保险始终生效：时长差 >35 秒、候选带目标没有的版本标记（Live/Remix/伴奏/DJ版…），一律拒绝。

> 注意：网易云对**未登录请求系统性压制部分曲库**（如周杰伦：搜索/歌手热门/专辑三路都查不到，
> 但按 ID 直查正常）。这类原唱只能靠 ID 命中，无法通过搜索找回。

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
