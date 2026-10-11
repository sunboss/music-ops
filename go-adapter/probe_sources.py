"""
音源体检：在东京服务器上逐个来源测试中文歌能否拿到可用直链
判定标准：严格匹配通过 + 返回 http(s) 链接（不接受 "None"/空串）
"""
import json
import urllib.error
import urllib.parse
import urllib.request

ADAPTER = "http://go-adapter:8811"
SOURCES = ["kuwo", "migu", "kugou", "qq", "bilibili", "qianqian", "soda", "fivesing", "netease", "jamendo"]
SONGS = [("晴天", "周杰伦", 269), ("孤勇者", "陈奕迅", 256)]


def try_source(name, artist, dur, src):
    q = urllib.parse.urlencode({"name": name, "artist": artist, "duration": str(dur), "sources": src})
    try:
        with urllib.request.urlopen(ADAPTER + "/resolve-best?" + q, timeout=35) as r:
            d = json.loads(r.read().decode())
        u = d.get("url") or ""
        good = u.startswith("http://") or u.startswith("https://")
        return ("OK" if good else "无效链接"), u[:70], d.get("attempts")
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode())
            att = d.get("attempts") or []
            return "无匹配", "", att[0].get("status") if att else str(e.code)
        except Exception:
            return "HTTP %s" % e.code, "", None
    except Exception as e:
        return "异常", str(e)[:60], None


print("%-10s %-22s %-10s %s" % ("来源", "歌曲", "结果", "详情"))
print("-" * 100)
summary = {}
for name, artist, dur in SONGS:
    for src in SOURCES:
        verdict, url, extra = try_source(name, artist, dur, src)
        summary.setdefault(src, []).append(verdict)
        print("%-10s %-22s %-10s %s" % (src, "%s/%s" % (name, artist), verdict, url or extra))

print()
print("== 可用性汇总（两首歌都 OK 才算可用）")
for src, vals in summary.items():
    ok = all(v == "OK" for v in vals)
    print("  %-10s %s  %s" % (src, "可用" if ok else "不可用", vals))
