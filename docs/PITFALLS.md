# 踩坑存档（PITFALLS）

> 目的：**同一类错误只允许犯一次**。每条都写清「现象 → 根因 → 以后的规则」。
> 添加新条目请只写教训和规则，不要写成事故日记；能自动化拦住的，就写成脚本里的检查。

---

## A. 部署与运维

### A1 模糊 patch 把类名改掉，服务启动即崩
- **现象**：上线后 enhancer 崩溃重启，日志 `NameError: name 'H' is not defined`，全站 `/api/*` 502。
- **根因**：补丁工具是模糊匹配；原文是 `class H(BaseHTTPRequestHandler)`，我的锚点写的是
  `class Handler(...)`，于是"替换"实际变成了改名，而文件末尾仍用 `H(...)` 启动。
- **规则**：① 每次上线前跑 `python3 -m pyflakes`；② 提交前看 `git diff --stat`，
  **预期是纯新增**（出现删除行就要逐条核对）；③ 部署脚本必须能自动回滚。

### A2 部署脚本用固定 sleep 等就绪 → 把成功部署误判成失败并回滚
- **现象**：新代码本身没问题，健康检查全 502，脚本自动回滚。
- **根因**：容器重启后绑定端口比固定 9 秒慢；且边缘在重启窗口内必然短暂 5xx。
- **规则**：**轮询就绪**（`docker exec` 内打 `/health`，最多 60 秒），健康检查**每个端点重试 3 次**，
  再判失败。已固化在 `go-adapter/deploy_enhancer.sh`。

### A3 改了 `docker-compose.yml` 的环境变量，`restart` 不生效
- **现象**：代码里新的默认值生效了，但 `FALLBACK_SOURCES` 还是旧的两个平台。
- **根因**：`docker compose restart` 只是重启进程，**不重读 compose 配置**。
- **规则**：改 env / volumes / ports 一律用 `docker compose up -d <svc>`（会重建容器）。

### A4 容器重建后 nginx 502（上游 IP 变了）
- **现象**：`docker exec` 内部访问 enhancer 正常，公网/nginx 502。
- **根因**：nginx 只在启动时解析一次 `enhancer` 主机名；重建容器换了 IP，nginx 仍打旧 IP。
- **规则**：重建上游容器后 `docker exec music-web nginx -s reload`。

### A5 `pkill -f xxx` 把执行它的 ssh 会话自己杀掉
- **现象**：`ssh host 'pkill -f probe.sh; ...'` 返回 255、无任何输出。
- **根因**：`pkill -f` 匹配**完整命令行**，而我的 ssh 命令行里就含 `probe.sh` → 自杀。
- **规则**：用括号技巧 `pkill -f "probe_[m]atrix.sh"`，或按 PID 杀。

### A6 长任务在 ssh 里后台化不可靠
- **现象**：`nohup/setsid ... &` 时而成功、时而 ssh 255 无输出。
- **规则**：能前台跑就前台跑（`timeout` 给足）；必须后台时写日志文件再轮询文件，
  不要依赖 ssh 的返回码判断"是否启动"。

### A7 国内 → 东京方向没有 SSH 密钥
- **现象**：在国内机上 `ssh 东京 "cat > /dev/null"` 报 Permission denied，
  但命令里的计时照跑 → 得出"20MB/2.5s"的**假数据**。
- **规则**：测跨机带宽要**先验证链路真的通了**（比对字节数），再报数字；测生产路径优先。

---

## B. 音源与播放

### B1 网易云不是可靠音源（本项目的起点问题）
- **现象**：未登录请求被系统性压制（整歌手曲库查不到）、VIP 曲只给 30 秒试听、灰歌无法播放。
- **决策**：**音源改用自有 Go 引擎（多平台）**，网易云只保留"目录"角色（歌单/专辑/歌词/封面/推荐）。
  见 ADR-1；代码里 `ALLOW_OFFICIAL=0` 默认关闭网易云直链。

### B2 直链有寿命，缓存它只会换来 403
- **现象**：同一首歌偶发 `落盘失败: HTTP Error 403 Forbidden`，日志出现「直链过期(403)，重新解析」。
- **根因**：国内平台直链以分钟计过期；而旧实现把"上次解析出的直链"当候选排在最前。
- **规则**：**不要缓存直链当候选**；重新解析只要 0.1–0.2 秒（实测），永远用新鲜的。
  真值得复用/落盘的是**音频文件本身**（整曲落盘 + 时长体积校验）。

### B3 落盘失败要立刻重解析，而不是退缩成流式代理
- **规则**：`fetch_error` 且来源是 Go 引擎时，重新解析一次再试；否则用户看到的是"这歌放不了"。

### B4 取流必须带平台 Referer
- **现象**：部分平台直链直接 403。
- **规则**：按 URL 主机自动补 Referer（kuwo/kugou/qq/netease/migu/bilibili/joox/抖音系），
  落盘、Range 探测、流式代理、HEAD 探测**四处统一**（`stream_headers()`）。

### B5 平台可用性必须实测，不能看文档
- **实测（CN 原生 IP，5 首 × 11 平台）**：kuwo 取到 4/5 真直链；kugou 5/5 匹配但仅 1/5 出链；
  qq / netease(库内) 各 1/5；joox/jamendo/bilibili/千千/汽水/5sing 对这些主流歌 0–1 匹配；
  **migu 每次 30 秒超时 → 从列表摘掉**（否则每次失败白等 30 秒）。
- **规则**：平台顺序是运维参数（`FALLBACK_SOURCES`），改它要配一组实测数据。

### B6 "海外服务器不行"要先分清是取链还是取字节
- **实测**：东京**直取**国内直链 4,317,292 字节 @ **9.1 MB/s**（完全没问题）；
  经国内适配器 `/fetch` 代抓同样字节 @ **335 KB/s**（慢 43 倍，只作兜底）。
- **规则**：先量再改架构；不要因为个别 403 就把整站搬到国内。

### B7 片段伪装成整曲
- **规则**：只在字节上判成败——真实解码时长 + 体积双校验（容差 8 秒），
  拒绝时**继续试下一个候选**，全部失败才标记"无可用音源"并定期复核自愈。

---

## C. 验收脚本自身的坑（这些最容易被误判成产品 bug）

| 现象 | 根因 | 规则 |
|---|---|---|
| 双击列表行没反应 | 虚拟滚动容器里首个子元素是占位层，`.row:nth-child(1)` 匹配不到 | 用 `querySelector('.row')`，别用 `nth-child` |
| 点播放入口无效 | 行内按钮 `display:none`，只有 hover 才显示 | 用行的双击（`clickCount` 1 然后 2）或先让它可见 |
| 点视口外的元素落空 | 元素在可视区外，坐标点不到 | 点击前 `scrollIntoView({block:'center'})` |
| 拿不到播放状态 | `<audio>` 是程序创建、**不在 DOM 里**；且 Pinia 的 state 对象上没有 action | 读 store 实例 `$pinia._s.get('player')` 的 `progress/queue/index` |
| 报"没有元素"其实是页面没加载完 | 1000 行歌单渲染慢 | 轮询等元素出现，再断言 |
| `HEAD` 探测返回 501/挂住 | 服务端没实现 `do_HEAD`；用替换 `wfile` 的写法还会把响应头一起吞掉 | 实现 `do_HEAD`，只拦响应体（`_wbody`） |

---

## D. 投屏

### D1 Safari 的 AirPlay 选择器必须**同步**调用
- **现象**：点按钮完全没反应，也不报错。
- **根因**：先 `await el.play()` 再调 `webkitShowPlaybackTargetPicker()`，
  `await` 一让步，用户手势上下文失效，WebKit **静默忽略**调用。
- **规则**：同一个 tick 内先调选择器，播放放后面异步做。

### D2 Chrome 看不到 AirPlay 设备；公网页面访问 127.0.0.1 会被拦
- **现象**：`Permission was denied for this request to access the loopback address space`（Chrome）；
  Safari 按混合内容拦。
- **规则**：按设备能力渲染（Safari→系统选择器；Chrome→Cast 或小菜单）；
  小桥被拦时给"去开本地网络访问"，**不要**靠改安全开关蒙过验收。

### D3 别把网关当投屏设备
- **现象**：桥日志"发现 1 台 DLNA 渲染器"，看起来网络里有 DLNA 设备。
- **真相**：`192.168.1.158`/`.1` 是**华为网关**（`InternetGatewayDevice` +
  `www-huawei-com:NetworkSyncService`，描述请求对任何 UA 都 403）；那条"1 台"是我自己的模拟渲染器。
- **规则**：只看 `urn:schemas-upnp-org:device:MediaRenderer:1` 且描述可取的设备才算投屏目标。

---

## E. 文档与协作

### E1 定位别停留在旧形态
- **规则**：这是**自研的 AI 音乐系统**（自研前端 + 自有 Go 音源引擎 + 大模型编排），
  不是"给 YesPlayMusic 打补丁"。动手前先读 `README.md` 与 `docs/AI-MUSIC-SYSTEM.md`。

### E2 聊天里的结论不算数
- **规则**：决策写进 `README.md` / `docs/AI-MUSIC-SYSTEM.md`（ADR），教训写进本文。
  改结论要改文档，不能只在聊天里说。

### E3 密钥
- **规则**：只从环境变量/文件读（`600`），不进代码、日志、仓库、聊天；聊天里出现过的密钥应重置。
