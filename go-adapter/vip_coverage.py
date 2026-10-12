"""
VIP 歌曲可播放率实测：采样一批歌曲，逐首走完整链路（取源 → 下载 → 解码真实时长），
统计「完整播放 / 无完整音源」的比例，并确认不再出现任何试听片段。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"
KEYS = ["周杰伦", "林俊杰", "陈奕迅", "邓紫棋", "薛之谦", "李荣浩", "毛不易", "单依纯",
        "张杰", "汪苏泷", "许嵩", "王菲", "张学友", "周深", "华晨宇", "张碧晨", "孙燕姿", "莫文蔚"]


def jget(path, timeout=180):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


ids, seen = [], set()
for kw in KEYS:
    try:
        d = jget("/api/search?keywords=%s&type=1&limit=6" % urllib.parse.quote(kw))
        for s in ((d.get("result") or {}).get("songs") or []):
            if s.get("id") and s["id"] not in seen:
                seen.add(s["id"])
                ids.append(str(s["id"]))
    except Exception:
        pass

print("采样歌曲:", len(ids), "首\n")
stat = {"完整": 0, "无完整音源": 0, "片段(已拒)": 0, "异常": 0}
by_src = {}
bad = []
for sid in ids:
    name, artist, album, dur = server.song_detail(sid)
    try:
        u = jget("/api/song/url?id=%s" % sid)
        it = (u.get("data") or [{}])[0]
        url = it.get("url")
        src = it.get("source") or "-"
        if not url:
            stat["无完整音源"] += 1
            bad.append((name, artist, dur, "无音源"))
            continue
        with urllib.request.urlopen(url if url.startswith("http") else BASE + url, timeout=200) as r:
            body = r.read()
        open("/tmp/cov.bin", "wb").write(body)
        actual = server.probe_duration("/tmp/cov.bin")
        if dur and actual and actual < dur - 8:
            stat["片段(已拒)"] += 1
            bad.append((name, artist, dur, "仍是片段 %.0f秒" % actual))
        elif actual <= 0 and url.find("no-source") >= 0:
            stat["无完整音源"] += 1
            bad.append((name, artist, dur, "无音源"))
        else:
            stat["完整"] += 1
            by_src[src] = by_src.get(src, 0) + 1
    except urllib.error.HTTPError as e:
        stat["无完整音源"] += 1
        bad.append((name, artist, dur, "HTTP %s (无音源)" % e.code))
    except Exception as e:
        stat["异常"] += 1
        bad.append((name, artist, dur, str(e)[:30]))

total = sum(stat.values())
print("结果:", stat)
print("可完整播放比例: %.1f%%" % (100.0 * stat["完整"] / total if total else 0))
print("来源分布:", by_src)
print()
print("无法完整播放的曲目（这些会被播放器跳过）：")
for b in bad[:30]:
    print("   %-24s %-14s 期望%-5s %s" % (str(b[0])[:22], str(b[1])[:12], b[2], b[3]))
if len(bad) > 30:
    print("   … 共 %d 首" % len(bad))
