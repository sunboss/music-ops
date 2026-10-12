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
