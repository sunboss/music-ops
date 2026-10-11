# go-adapter —— 严格匹配换源适配器

R-Music 的换源接入层。上游项目 **不是** 本仓库，而是
[`guohuiyuan/go-music-dl`](https://github.com/guohuiyuan/go-music-dl)（AGPL-3.0）。

本目录只放**我们自己写的适配器代码与验收脚本**；上游源码不入库。

## 它做什么

在音乐库（`github.com/guohuiyuan/music-lib`）之上包一层 HTTP 接口，
把「搜索 → 严格匹配 → 取直链」变成一个可控、可观测的服务：

| 接口 | 用途 |
|---|---|
| `GET /resolve?name=&artist=&album=&duration=&sources=` | 返回每个来源的候选、拒绝原因与逐个状态 |
| `GET /resolve-url?name=&artist=&duration=&source=` | 单来源取直链，失败时给出明确原因 |
| `GET /resolve-best?name=&artist=&duration=&sources=` | 依次尝试各来源，返回第一个严格匹配的直链 |
| `GET /healthz` | 健康检查，含已注入 Cookie 的来源名（不泄露取值） |

## 严格匹配规则（`main.go` 的 `match()`）

- **歌名 + 版本必须完全一致** —— 防翻唱、防 Live/Remix 混入
- **歌手允许平台写法差异** —— 多歌手分隔符、`feat.`、大小写、包含关系都算匹配
- **专辑名不参与判定** —— 各平台专辑名写法差异极大，硬判会误杀大量可播放曲目
- **时长必须吻合（±3 秒）** —— 区分原曲 / 翻唱 / 30 秒试听片段最可靠的依据
- 传入 `IsVIP` 的候选在没有凭证时拒绝（`entitlement_not_verified`）

## 国内出口（必须）

国内平台（酷我等）的签名直链接口**只对国内 IP 返回真实地址**，从东京直连会返回字符串 `"None"`。
因此适配器容器必须配代理，指向东京宿主机上的 `music-cn-relay.service`（SOCKS5 over SSH）：

```
HTTP_PROXY=socks5h://172.19.0.1:11080
HTTPS_PROXY=socks5h://172.19.0.1:11080     # 必须同时设置，只设一个不生效
```

音频文件本身东京可以直连，所以只有「取直链」这一步走隧道。

## 构建

适配器依赖上游库，需要在**上游仓库的目录树内**编译：

```bash
git clone https://github.com/guohuiyuan/go-music-dl
cd go-music-dl
git checkout c1b188c366ece39cb19a61d108e4fbf7c29271e5
cp -r /path/to/music-ops/go-adapter/cmd/phase2-adapter cmd/
go test ./cmd/phase2-adapter
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o adapter-linux-amd64 ./cmd/phase2-adapter
```

`build-and-deploy.sh` 封装了上述步骤与上传、重启流程。

## 验收脚本

| 脚本 | 作用 |
|---|---|
| `e2e_verify.py` | 端到端：取源 → 完整拉取 → 解码真实时长 → 与歌曲时长比对（在 enhancer 容器内跑） |
| `sweep_fallback.py` | 只挑走换源的曲目，逐首核对文件真实时长 |
| `hunt_short.py` | 猎捕「官方返回试听片段」的曲目 |
| `album_check.py` | 逐首体检指定专辑 |
| `run_diag_page.py` | 用真实 Chrome 加载站点上的 `/diag.html`，读回播放结论 |
| `live_play_verify.py` | 真实浏览器播放验收（起播 / 拖动 / 播到结尾） |
| `diag_upstream.py` | 本机（上海）与东京的地域差异对照 |

判定红线：**文件真实时长 < 歌曲时长 − 8 秒 → 视为试听片段，绝不可播放**。
