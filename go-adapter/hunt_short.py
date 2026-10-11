"""
猎捕：找出「官方接口返回试听片段」的歌曲（这是手机上只播 30 秒的根源候选）。
对每首歌：取官方直链 -> 实际下载 -> 解码真实时长 -> 与歌曲时长比对。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"
KEYS = ["周杰伦", "林俊杰", "陈奕迅", "邓紫棋", "薛之谦", "李荣浩", "毛不易", "单依纯",
        "张杰", "汪苏泷", "许嵩", "王菲", "张学友", "刘德华", "五月天", "周深", "华晨宇", "张碧晨"]


def jget(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


ids, seen = [], set()
for kw in KEYS:
    try:
        d = jget("/api/search?keywords=%s&type=1&limit=8" % urllib.parse.quote(kw))
        for s in ((d.get("result") or {}).get("songs") or []):
            if s.get("id") and s["id"] not in seen:
                seen.add(s["id"])
                ids.append(s["id"])
    except Exception:
        pass
print("取样:", len(ids), "首")

short, official, nooff = [], 0, 0
for sid in ids:
    sid = str(sid)
    name, artist, album, dur = server.song_detail(sid)
    off, _ = server.official_url(sid)
    if not off:
        nooff += 1
        continue
    official += 1
    try:
        req = urllib.request.Request(off, headers={"User-Agent": server.UA_BROWSER})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        open("/tmp/hunt.bin", "wb").write(body)
        actual = server.probe_duration("/tmp/hunt.bin")
        flag = ""
        if dur and actual and actual < dur - 8:
            flag = "★ 片段"
            short.append((sid, name, artist, dur, round(actual, 1), len(body)))
        if flag or (dur and actual and actual < dur - 3):
            print("%-16s %-10s 歌曲%4ss 文件%6.1fs %s %d字节" %
                  (name[:14], artist[:8], dur, actual, flag, len(body)))
    except Exception as e:
        print("%-16s 官方直链下载失败: %s" % (name[:14], str(e)[:40]))

print()
print("官方有直链 %d 首 / 无直链 %d 首" % (official, nooff))
print("发现官方试听片段:", len(short))
for s in short:
    print("   id=%s %s - %s 歌曲%ss 实际%ss" % s)
