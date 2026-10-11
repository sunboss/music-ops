"""
查漏：官方直通路径是否会把「30 秒试听直链」原样透传给播放器。
对每首歌：取 /api/song/url → 若返回的是官方直链（非我们的代理），实际下载并核对真实时长。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"
ARTISTS = ["周杰伦", "陈奕迅", "林俊杰", "薛之谦", "李荣浩", "邓紫棋"]


def jget(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


ids, seen = [], set()
for kw in ARTISTS:
    try:
        d = jget("/api/search?keywords=%s&type=1&limit=12" % urllib.parse.quote(kw))
        for s in ((d.get("result") or {}).get("songs") or []):
            if s.get("id") and s["id"] not in seen:
                seen.add(s["id"])
                ids.append(s["id"])
    except Exception as e:
        print("搜索失败", kw, str(e)[:40])

meta = {}
for i in range(0, len(ids), 50):
    try:
        d = jget("/api/song/detail?ids=%s" % ",".join(str(x) for x in ids[i:i + 50]))
        for s in (d.get("songs") or []):
            meta[s.get("id")] = (s.get("name", ""), round((s.get("dt") or 0) / 1000.0, 1),
                                 (s.get("fee") if s.get("fee") is not None else -1))
    except Exception as e:
        print("详情失败", str(e)[:40])

print("候选:", len(ids))
print("%-20s %-8s %-6s %-9s %-9s %s" % ("歌曲", "歌曲时长", "fee", "文件时长", "判定", "路径"))
print("-" * 80)
bad, official_cnt, fallback_cnt, none_cnt = [], 0, 0, 0
for sid in ids:
    name, dt, fee = meta.get(sid, ("?", 0, -1))
    try:
        d = jget("/api/song/url?id=%s&br=320000" % sid)
        it = (d.get("data") or [{}])[0]
        url = it.get("url")
        if not url:
            none_cnt += 1
            continue
        is_proxy = url.startswith("/api/audio/proxy")
        path = "我们的代理" if is_proxy else "官方直通"
        if is_proxy:
            fallback_cnt += 1
        else:
            official_cnt += 1
        with urllib.request.urlopen(url if url.startswith("http") else BASE + url, timeout=180) as r:
            body = r.read()
        open("/tmp/chk2.bin", "wb").write(body)
        actual = server.probe_duration("/tmp/chk2.bin")
        if actual <= 0:
            verdict = "解析不出"
        elif dt and actual < dt - 8:
            verdict = "★★ 片段!"
            bad.append((name, dt, actual, path))
        else:
            verdict = "完整"
        if path == "官方直通" and verdict != "完整":
            print("%-20s %-8s %-6s %-9s %-9s %s" % (name[:18], dt, fee, round(actual, 1), verdict, path))
    except Exception as e:
        print("%-20s 异常 %s" % (name[:18], str(e)[:40]))

print()
print("官方直通 %d 首 / 我们的代理 %d 首 / 无音源 %d 首" % (official_cnt, fallback_cnt, none_cnt))
print("发现短片段:", bad if bad else "无")
