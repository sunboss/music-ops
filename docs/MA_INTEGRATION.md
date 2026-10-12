# Music Assistant / Home Assistant 接入 R-Music

> 目标：让 HAOS 里的 **Music Assistant** 直接播放 R-Music 的歌（含 AI 一句话点歌）。
> 我方（R-Music）侧的接口已全部上线并实测通过；HA/MA 侧需要有人登录 HA 操作。

## 0. 现状与前提

| 项 | 状态 |
|---|---|
| Music Assistant | `2.10.6`，`http://192.168.1.240:8095`，**`onboard_done: false`（还没初始化）** |
| Home Assistant | 与 MA 同机（MA 是 HA 的 add-on）；`192.168.1.240:8123` 从外网侧探测不通，需在内网/HA 界面操作 |
| R-Music 接口 | `https://music.1234r.com/api/ma/*` 已上线，本文末尾列出实测结果 |

**必须先完成 MA 初始化**（打开 `http://192.168.1.240:8095` → 设置存储/创建管理员 → 添加播放器），否则下面任何方式都接不上。

## 1. 三种接入方式（按推荐顺序）

### 方式 1｜一个 URL = 一句话点歌（最省事，无需改 HA 配置）

| 端点 | 用途 |
|---|---|
| `GET /api/ma/play?id=186016` | 按歌曲 ID 直接出音频流（毫秒级） |
| `GET /api/ma/play?q=周杰伦的晴天` | 一句话点歌 → 直接出音频流（走 AI，10–40 秒） |
| `GET /api/ma/resolve?q=…` / `?id=…` | 只取 JSON 元数据：标题/歌手/专辑/时长/封面/直链 |
| `GET /api/ma/m3u?q=深夜写代码听的` | M3U 播放清单（也支持 `?pid=<歌单id>`、`?aid=<专辑id>`） |

在 HA 里播放（任意 MA 播放器实体）：

```yaml
service: media_player.play_media
target:
  entity_id: media_player.你的播放器
data:
  media_content_id: "https://music.1234r.com/api/ma/play?id=186016"
  media_content_type: "music"
```

要点：
- 这个 URL **直接返回音频**（不是 302 跳转），支持 `Range`，MA 的 ffmpeg 能 seek；
- 若 MA 提示不支持该 media type，改用 `music_assistant.play_media` 服务，参数相同。

### 方式 2｜AI 一句话点歌接入 HA 脚本 / 语音助手

```yaml
# configuration.yaml
rest:
  - resource_template: >-
      https://music.1234r.com/api/ma/resolve?q={{ states('input_text.r_music_query') | urlencode }}
    scan_interval: 86400          # 只手动刷新，避免轮询消耗 AI 额度
    sensor:
      name: r_music_resolve
      value_template: "{{ value_json.title }}"
      json_attributes:
        - url
        - artist
        - album
        - duration
        - cover

input_text:
  r_music_query:
    name: 想听什么

script:
  r_music_ai_play:
    alias: R-Music AI 点歌播放
    fields:
      query:
        description: 想听什么（一句话）
      player:
        description: 播放器实体
        default: media_player.music_assistant
    sequence:
      - service: input_text.set_value
        target: { entity_id: input_text.r_music_query }
        data: { value: "{{ query }}" }
      - service: homeassistant.update_entity            # 触发一次取数
        target: { entity_id: sensor.r_music_resolve }
      - wait_template: "{{ state_attr('sensor.r_music_resolve','url') is not none }}"
        timeout: "00:02:00"
      - service: media_player.play_media
        target: { entity_id: "{{ player }}" }
        data:
          media_content_id: "{{ state_attr('sensor.r_music_resolve','url') }}"
          media_content_type: "music"
          extra:
            title: "{{ states('sensor.r_music_resolve') }}"
```

对 HA 的 Assist（语音/文字）说「帮我放周杰伦的慢歌」时，让它调用 `script.r_music_ai_play`。

### 方式 3｜当作本地曲库（把已落盘的整曲共享给 MA）

R-Music 播放过的整曲会落盘在东京服务器 `/data/sunboss/music/data/audio_cache/`（按歌曲 ID 命名）。

1. 在东京服务器把该目录以 **只读** SMB/NFS 暴露（或用 rsync 同步到 HA 主机的一个目录）；
2. MA → 设置 → 添加音乐提供方 → **Filesystem（本地/网络文件夹）** → 指向挂载点；
3. MA 扫描后即可像本地曲库一样浏览/排队。

> 注意：缓存文件不带完整 ID3 标签，MA 只能按文件名显示。要标签齐全就需要额外做一次元数据导出（可以再加接口）。

## 1b. 把 R-Music 变成 MA 的曲库（Filesystem 提供方）—— 「怎么添加我们的数据」

**先说清为什么不能直接填我们的接口**：Music Assistant **没有"通用 HTTP/JSON"提供方**。
它接受的是 Spotify/Tidal/Qobuz/Deezer/YouTube Music/Apple Music/SoundCloud/Plex/Jellyfin/
Subsonic/radio-browser，以及 **Filesystem（本地或网络文件夹）**。
所以要把我们的数据变成 MA 的曲库，唯一务实的路是：**把它做成一个"带标签的文件夹"**。

### 三步

**① 服务器上生成带标签曲库**（工具：`tools/build-library.py`，已跑过一次）

```bash
# 东京机；用 Docker 跑，不污染宿主机
docker run --rm -v /data/sunboss/music/data:/data -v /data/sunboss/music/tools:/tools \
  python:3.11-alpine sh -c "pip install -q mutagen && python /tools/build-library.py \
    --cache /data/audio_cache --out /data/library"
```

它做四件事：读缓存里的 `<歌曲ID>.<ext>` → 用网易云（目录层）换到 标题/歌手/专辑/年代/封面 →
写入标签（MP3→ID3v2.3、FLAC→Vorbis Comment、M4A→MP4 atoms）并嵌入封面 →
另存为 `歌手 - 歌名.ext` + 生成 `library.m3u8`。

实测：**56 首全部带标签，405 MB**；顺带发现并纠正了 **11 个扩展名与实际容器不符**的文件
（上游 Content-Type 谎报，例如 `.aac` 里其实是 M4A）——服务端落盘逻辑已一并修正，以后不会再产生。

**② 同步到 MA 能读到的地方**（工具：`tools/library-sync.sh`，本机跑）

```bash
bash tools/library-sync.sh                 # 默认同步到 ~/Music/R-Music
TARGET=/Volumes/media/R-Music bash tools/library-sync.sh   # 或直接同步到 HA 的 media 共享
```

实测：424 MB / 55 首，从东京拉回约 2.3 MB/s。
**为什么是"拉"不是"推"**：本机有到服务器的密钥、服务器没有到本机的，而且**不需要把 SMB/NFS
暴露到公网**（445/2049 是被扫描最凶的端口）。

**③ 在 Music Assistant 里添加**

```
MA → 设置 → 添加音乐提供方 → Filesystem（本地/网络文件夹）→ 路径填上一步的目录 → 保存并扫描
```

- MA 与 HA 同机（HAOS 插件）时：**最省事是把曲库放进 HA 的 `/media` 目录**（MA 插件可直接读），
  即把 ② 的 TARGET 指向 HA 的 media 共享，或把同步脚本放到 HA 上跑；
- MA 的 Filesystem 提供方也支持 **SMB/NFS 路径**，但那就等于让 MA 跨海读东京的文件——能通但慢，
  不如在本机留一份。

### 注意事项（不隐瞒）

- 曲库 = **我们播放过的整曲**，不是全网曲库。新歌要先播过一次才会进曲库（这恰好也是"听过的都在本地"）。
- 要"按歌单/专辑批量拉整张"是另一件事（需要一个批量导出任务：遍历歌单 → 逐首落盘 → 重建曲库）。
- 标签是写进文件里的，之后任何支持读标签的播放器（Plex/Jellyfin/Navidrome/MA）都能正确认歌。

## 2. 语音助手（可选）

如果 HA 接了 Assist / 小爱 / HomePod，可用一个 `input_text` + 上面的脚本实现「说一句就放歌」。
R-Music 站内已支持浏览器语音点歌，HA 侧只需调用上面的 script。

## 3. 我方接口实测记录（上线后）

| 检查 | 结果 |
|---|---|
| `HEAD /api/audio/proxy?id=…` | **200** + `content-type: audio/mpeg` + `content-length` + `accept-ranges: bytes`（此前返回 501，MA/ffmpeg 会直接失败 —— 已修） |
| `GET /api/audio/proxy?id=…` + `Range: bytes=0-1023` | **206** + `content-range: bytes 0-1023/4147255` ✓ 可拖动 |
| `GET /api/ma/resolve?id=186016` | 200 `{ok,title,artist,album,duration,cover,url,stream}` ✓ 秒回 |
| `GET /api/ma/play?q=…` | 206 + Range ✓（一句话点歌直接出音频） |
| `GET /api/ma/m3u?pid=24381616` | `#EXTM3U` + 逐条 `#EXTINF:时长,歌手 - 歌名` + 音频直链 ✓ |
| 防盗链 | 外部站点 Referer → 403；MA/HA（服务端请求，无 Referer）与局域网 → 放行 ✓ |

## 4. 已知限制（不隐瞒）

- **网易云对未登录请求会压制部分歌手曲库**（例如周杰伦的录音室版），这时一句话点歌可能只能拿到 Live/翻唱版本或换源结果；系统不会伪造音源，找不到就明确报错。
- 一句话点歌（`q=`）走大模型检索 + 多平台探活，**首次 10–40 秒**；用 `?id=` 或歌单参数则是毫秒级。
- 音频走东京节点（`64.83.34.204`），HA 主机在国内访问会有跨境延迟，首播约 1–3 秒。
