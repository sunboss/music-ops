"""验证：能否用「专辑曲目」找回被搜索压制的原唱（大模型提供专辑名）"""
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


def find_in_album(album_kw, want_title, want_artist):
    d = get("/cloudsearch", keywords=album_kw, type=10, limit=5)
    albs = ((d.get("result") or {}).get("albums") or [])
    print("   专辑搜索 %r -> %d 个结果" % (album_kw, len(albs)))
    for a in albs[:3]:
        ar = (a.get("artist") or {}).get("name")
        print("      %s / %s / id=%s" % (a.get("name"), ar, a.get("id")))
    for a in albs[:3]:
        det = get("/album", id=a.get("id"))
        songs = (det.get("songs") or [])
        for s in songs:
            if server._norm_loose(s.get("name")) == server._norm_loose(want_title):
                names = "/".join(x.get("name", "") for x in (s.get("ar") or []))
                if server._norm_loose(want_artist) in server._norm_loose(names) or True:
                    print("   ✔ 专辑《%s》里找到: %s / %s / %s秒 / id=%s"
                          % (a.get("name"), s.get("name"), names,
                             (s.get("dt") or 0) // 1000, s.get("id")))
                    return s
    return None


print("=== 大模型给的目标（假设）：歌=晴天 歌手=周杰伦 专辑=叶惠美")
r = find_in_album("叶惠美", "晴天", "周杰伦")

print("\n=== 对照：直接查 id=186016")
print("   ", server.song_detail("186016"))

print("\n=== 再测一个：稻香 / 周杰伦（专辑《魔杰座》）")
find_in_album("魔杰座", "稻香", "周杰伦")
