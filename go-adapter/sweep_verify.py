"""
覆盖率验收 v2：从真实榜单取歌，逐首用 /api/song/detail 拿到准确时长，
再实际下载换源音频，比对「文件真实时长 vs 歌曲时长」。
差值 > 8 秒即判定为试听片段 / 占位音频被当成完整曲目播放（用户看到的『只播 30 秒』）。
"""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"


def jget(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pick_ids():
    """优先榜单，取不到再退回搜索"""
    ids = []
    for path in ("/api/toplist/detail", "/api/personalized/newsong"):
        try:
            d = jget(path)
        except Exception as e:
            print("  %s 不可用: %s" % (path, str(e)[:40]))
            continue
        for pl in (d.get("list") or []):
            for t in (pl.get("tracks") or [])[:8]:
                if t.get("id"):
                    ids.append(t["id"])
        for s in (d.get("result") or []):
            sid = s.get("id") or (s.get("song") or {}).get("id")
            if sid:
                ids.append(sid)
        if ids:
            break
    if not ids:
        d = jget("/api/search?keywords=%s&limit=20" % urllib.parse.quote("周杰伦"))
        for s in ((d.get("result") or {}).get("songs") or []):
            if s.get("id"):
                ids.append(s["id"])
    out = []
    for i in ids:                      # 去重保序
        if i not in out:
            out.append(i)
    return out[:14]


ids = pick_ids()
print("取样歌曲数:", len(ids))
if not ids:
    raise SystemExit("取不到歌曲 id")

# 准确时长以 song/detail 为准
meta = {}
try:
    d = jget("/api/song/detail?ids=%s" % ",".join(str(i) for i in ids))
    for s in (d.get("songs") or []):
        ar = ", ".join(a.get("name", "") for a in (s.get("ar") or []))
        meta[s.get("id")] = (s.get("name", ""), ar, round((s.get("dt") or 0) / 1000.0, 1))
except Exception as e:
    print("song/detail 失败:", e)

print("%-20s %-12s %-8s %-9s %-10s %s" % ("歌曲", "歌手", "歌曲时长", "文件时长", "判定", "来源"))
print("-" * 92)
stats = {"完整": 0, "片段": 0, "无音源": 0, "异常": 0}
for sid in ids:
    name, artist, dt = meta.get(sid, ("?", "?", 0))
    try:
        d = jget("/api/song/url?id=%s" % sid)
        it = (d.get("data") or [{}])[0]
        url = it.get("url")
        src = it.get("source") or ("官方" if url else "-")
        if not url:
            stats["无音源"] += 1
            print("%-20s %-12s %-8s %-9s %-10s %s" % (name[:18], artist[:10], dt or "-", "-", "无音源", src))
            continue
        t0 = time.time()
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
        print("%-20s %-12s %-8s %-9s %-10s %s (%.1fs)" % (
            name[:18], artist[:10], dt or "-", round(actual, 1), verdict, src, time.time() - t0))
    except Exception as e:
        stats["异常"] += 1
        print("%-20s %-12s %-8s %-9s %-10s %s" % (name[:18], artist[:10], dt or "-", "-", "异常", str(e)[:30]))

print()
print("统计:", stats)
