"""
针对性验收：只挑「走换源(fallback)」的歌曲，实际下载并核对真实时长。
判定：文件真实时长 < 歌曲时长 - 8 秒 => 试听片段/占位音频（用户看到的『只播 30 秒』）
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"
ARTISTS = ["周杰伦", "林俊杰", "陈奕迅", "邓紫棋", "薛之谦", "毛不易", "李荣浩", "单依纯"]


def jget(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


ids = []
for kw in ARTISTS:
    try:
        d = jget("/api/search?keywords=%s&type=1&limit=12" % urllib.parse.quote(kw))
        for s in ((d.get("result") or {}).get("songs") or []):
            if s.get("id") and s["id"] not in ids:
                ids.append(s["id"])
    except Exception as e:
        print("搜索失败", kw, str(e)[:40])
print("候选歌曲数:", len(ids))

meta = {}
for i in range(0, len(ids), 50):
    chunk = ids[i:i + 50]
    try:
        d = jget("/api/song/detail?ids=%s" % ",".join(str(x) for x in chunk))
        for s in (d.get("songs") or []):
            ar = ", ".join(a.get("name", "") for a in (s.get("ar") or []))
            meta[s.get("id")] = (s.get("name", ""), ar, round((s.get("dt") or 0) / 1000.0, 1))
    except Exception as e:
        print("详情失败:", str(e)[:50])

print()
print("%-20s %-12s %-8s %-9s %-9s %s" % ("歌曲", "歌手", "歌曲时长", "文件时长", "判定", "来源"))
print("-" * 88)
stats = {"完整": 0, "片段": 0, "无音源": 0, "异常": 0, "官方": 0}
for sid in ids:
    name, artist, dt = meta.get(sid, ("?", "?", 0))
    try:
        d = jget("/api/song/url?id=%s" % sid)
        it = (d.get("data") or [{}])[0]
        url = it.get("url")
        src = it.get("source")
        if not url:
            stats["无音源"] += 1
            continue
        if src != "fallback":
            stats["官方"] += 1
            continue
        with urllib.request.urlopen(url if url.startswith("http") else BASE + url, timeout=180) as r:
            data = r.read()
        open("/tmp/chk.bin", "wb").write(data)
        actual = server.probe_duration("/tmp/chk.bin")
        if actual <= 0:
            verdict = "无法解析"
            stats["异常"] += 1
        elif dt and actual < dt - 8:
            verdict = "片段!"
            stats["片段"] += 1
        else:
            verdict = "完整"
            stats["完整"] += 1
        print("%-20s %-12s %-8s %-9s %-9s %s" % (name[:18], artist[:10], dt or "-",
                                                 round(actual, 1), verdict, src))
    except Exception as e:
        stats["异常"] += 1
        print("%-20s %-12s %-8s %-9s %-9s %s" % (name[:18], artist[:10], dt or "-", "-", "异常", str(e)[:34]))

print()
print("统计:", stats)
print("（官方/无音源 不计入换源质量评估；重点是换源里的『片段!』数量）")
