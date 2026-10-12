"""验证：能否用「歌手热门歌曲」找回被搜索索引压制的原唱"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

B = server.MUSIC_API_UPSTREAM.rstrip("/")


def get(path, **q):
    u = B + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(u, headers={"User-Agent": server.UA_BROWSER,
                                             "Referer": "https://music.1234r.com/"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        return {"__err": str(e)[:80]}


print("=== 1) 搜索歌手拿 artist id（type=100）")
d = get("/cloudsearch", keywords="周杰伦", type=100, limit=3)
arts = ((d.get("result") or {}).get("artists") or [])
for a in arts:
    print("   %s / id=%s / 专辑%s 首" % (a.get("name"), a.get("id"), a.get("albumSize")))
aid = (arts[0] or {}).get("id") if arts else None

print("\n=== 2) 取该歌手热门歌曲")
if aid:
    d2 = get("/artists", id=aid)
    hot = (d2.get("hotSongs") or [])
    print("   热门歌曲 %d 首，前 8 首：" % len(hot))
    for s in hot[:8]:
        ar = "/".join(x.get("name", "") for x in (s.get("ar") or []))
        print("      %-26s %-18s %s秒 id=%s" % (str(s.get("name"))[:24], ar[:16],
                                                (s.get("dt") or 0) // 1000, s.get("id")))
    print("\n=== 3) 里面有没有原唱《晴天》")
    for s in hot:
        if server._norm_loose(s.get("name")) == server._norm_loose("晴天"):
            print("   ✔ 命中: %s / %s / %s秒 / id=%s"
                  % (s.get("name"), "/".join(x.get("name") for x in (s.get("ar") or [])),
                     (s.get("dt") or 0) // 1000, s.get("id")))
else:
    print("   拿不到 artist id")

print("\n=== 4) 对照：直接查 id=186016 是否就是我们能播的原唱")
print("   ", server.song_detail("186016"))
