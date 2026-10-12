"""评估「搜索补原唱」到底有没有用：对比补搜前后，原唱是否进了前面"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

B = server.MUSIC_API_UPSTREAM.rstrip("/")


def search(kw, limit=10):
    u = B + "/cloudsearch?" + urllib.parse.urlencode({"keywords": kw, "type": 1, "limit": limit})
    req = urllib.request.Request(u, headers={"User-Agent": server.UA_BROWSER,
                                             "Referer": "https://music.1234r.com/"})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return ((d.get("result") or {}).get("songs") or [])


def names(songs, n=5):
    out = []
    for s in songs[:n]:
        ar = "/".join(a.get("name", "") for a in (s.get("ar") or []))
        out.append("%s(%s)" % (s.get("name"), ar[:12]))
    return " | ".join(out)


CASES = [("晴天", "周杰伦"), ("十年", "陈奕迅"), ("红豆", "王菲"),
         ("消愁", "毛不易"), ("富士山下", "陈奕迅")]

for kw, artist in CASES:
    base = search(kw)
    extra = search(artist + " " + kw)
    base_has = server._has_artist_title(base, kw, artist)
    merged = server.merge_origin_first(extra, base, 10)
    print("【%s】目标原唱=%s" % (kw, artist))
    print("   原列表前5: %s" % names(base))
    print("   列表里已有原唱: %s" % ("是" if base_has else "否"))
    print("   补搜%s前5: %s" % (artist, names(extra)))
    print("   合并后前5: %s" % names(merged))
    print()
