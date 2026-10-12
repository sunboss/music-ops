"""诊断为什么搜索补原唱没触发"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

kw = "晴天"
u = "http://127.0.0.1:3001/api/search?keywords=%E6%99%B4%E5%A4%A9&type=1&limit=30"
d = json.loads(urllib.request.urlopen(u, timeout=30).read())
songs = (d.get("result") or {}).get("songs") or []
print("返回 %d 首：" % len(songs))
for i, s in enumerate(songs):
    ar = "/".join(a.get("name", "") for a in (s.get("ar") or []))
    print("  %2d. %-30s %-22s %s秒" % (i + 1, str(s.get("name"))[:28], ar[:20], s.get("dt", 0) // 1000))

print("\n=== 判定细节")
print("  _has_artist_title(列表, 晴天, 周杰伦) =", server._has_artist_title(songs, kw, "周杰伦"))
for s in songs:
    if server._norm_loose(s.get("name")) == server._norm_loose(kw):
        ar = " ".join(a.get("name", "") for a in (s.get("ar") or []))
        na = server._norm_loose("周杰伦")
        nar = server._norm_loose(ar)
        print("    同名曲: %r 歌手=%r  规范化歌手=%r  包含判定=%s"
              % (s.get("name"), ar, nar, (na in nar) if nar else "空"))

print("\n=== 补搜「周杰伦 晴天」会拿到什么")
extra = server.upstream_cloudsearch("周杰伦 晴天", 8)
for s in extra[:6]:
    ar = "/".join(a.get("name", "") for a in (s.get("ar") or []))
    print("    %-30s %-20s id=%s" % (str(s.get("name"))[:28], ar[:18], s.get("id")))
