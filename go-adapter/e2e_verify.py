"""
端到端验收：增强服务取源 -> 音频可完整拉取 -> 实测时长与歌曲本身时长吻合
在 music-enhancer 容器内运行（无 curl，纯 Python）
时长用 MPEG 帧游走解析（跳帧体），期望时长取自歌曲详情接口，避免硬编码
"""
import json
import urllib.request

BASE = "http://127.0.0.1:3001"
IDS = [("186016", "晴天"), ("1901371647", "孤勇者"), ("436514312", "告白气球"), ("1495784715", "给电影人的情书")]

SR_TAB = {0: 44100, 1: 48000, 2: 32000}
BR_TAB = {1: [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
          3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]}


def get(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()


def mp3_info(data):
    """按 MPEG 帧游走解析：正确跳过帧体，返回 (时长秒, 码率bps)"""
    i = 0
    if data[:3] == b"ID3":
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        i = 10 + size
    total, fps, br = 0.0, [], 0
    n = len(data)
    while i < n - 4:
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            ver = (data[i + 1] >> 3) & 0x03
            layer = (data[i + 1] >> 1) & 0x03
            bri = (data[i + 2] >> 4) & 0x0F
            sri = (data[i + 2] >> 2) & 0x03
            pad = (data[i + 2] >> 1) & 0x01
            if ver in (2, 3) and layer == 1 and 0 < bri < 15 and sri != 3:
                sr = SR_TAB[sri] * (2 if ver == 2 else 1)
                bitrate = BR_TAB[3 if ver == 3 else 1][bri] * 1000
                spf = 1152 if ver == 3 else 576
                flen = int(spf // 8 * bitrate / sr) + pad
                if flen <= 0:
                    break
                total += spf / float(sr)
                fps.append(bitrate)
                br = bitrate
                i += flen
                continue
        i += 1
    if not fps:
        return 0.0, 0
    avg = sum(fps) / float(len(fps))
    return total, int(avg)


def mp4_duration(data):
    """MP4/M4A：从 mvhd 原子读取时长"""
    i = data.find(b"mvhd")
    if i < 0:
        return 0.0
    ver = data[i + 4]
    if ver == 1:
        ts = int.from_bytes(data[i + 24:i + 28], "big")
        du = int.from_bytes(data[i + 28:i + 36], "big")
    else:
        ts = int.from_bytes(data[i + 16:i + 20], "big")
        du = int.from_bytes(data[i + 20:i + 24], "big")
    return du / float(ts) if ts else 0.0


def audio_info(data):
    """自动识别容器：MP4/M4A 走 mvhd，其余按 MPEG 音频帧解析"""
    if data[4:8] == b"ftyp":
        return mp4_duration(data), 0
    return mp3_info(data)


def expect_duration(sid):
    try:
        _, _, b = get(BASE + "/api/song/detail?ids=%s" % sid, timeout=30)
        s = (json.loads(b).get("songs") or [{}])[0]
        return round((s.get("dt") or 0) / 1000.0, 1)
    except Exception:
        return 0.0


print("%-14s %-6s %-9s %-11s %-11s %s" % ("歌曲", "HTTP", "码率", "实测时长", "接口时长", "结论"))
print("-" * 80)
fails = []
for sid, name in IDS:
    want = expect_duration(sid)
    try:
        _, _, body = get(BASE + "/api/song/url?id=%s" % sid)
        d = json.loads(body)
        url = (d.get("data") or [{}])[0].get("url") or ""
        if not url:
            fails.append(name)
            print("%-14s %-6s %s" % (name, "-", "无音源(未换到): " + json.dumps(d, ensure_ascii=False)[:60]))
            continue
        # 增强服务返回的是相对地址（/api/audio/proxy?...），补全为容器内可达地址
        full = url if url.startswith("http") else BASE + url
        # 先验证 Range 支持（播放器拖动进度依赖它）
        try:
            rq = urllib.request.Request(full, headers={"Range": "bytes=0-1023"})
            with urllib.request.urlopen(rq, timeout=60) as rr:
                range_code, range_len = rr.status, len(rr.read())
        except Exception as e:
            range_code, range_len = "错误", str(e)[:40]
        st, hdr, data = get(full, timeout=240)
        dur, br = audio_info(data)
        diff = abs(dur - want) if want else 99
        good = dur > 0 and len(data) > 300000 and (not want or diff <= 5)
        if not good:
            fails.append(name)
        print("%-14s %-6s %-9s %-11.2f %-11s %s" % (
            name, st, ("%dkbps" % (br // 1000)) if br else ("MP4/AAC" if data[4:8] == b"ftyp" else "?"), dur, want or "?",
            ("通过" if good else "不符") + " | %d 字节 | Range=%s(%s)" % (len(data), range_code, range_len)))
    except Exception as e:
        fails.append(name)
        print("%-14s 异常 %s" % (name, str(e)[:55]))

print()
print("总体:", "全部通过" if not fails else "未通过: %s" % ",".join(fails))
