"""量化 AI 辅助选源的机会：对严格匹配失败的歌，看各平台有没有同曲不同写法的候选"""
import json
import urllib.parse
import urllib.request

SONGS = [
    ("孤独Person", "马也Crabbit", "", 210),
    ("想你和我们的以后", "马也Crabbit", "", 235),
    ("Dear D", "陈壹千", "", 230),
    ("失眠了", "Sasablue", "", 195),
    ("甲乙丙丁", "李荣浩", "", 250),
]


def resolve(name, artist, dur, sources="kuwo,kugou,qq,migu"):
    q = urllib.parse.urlencode({"name": name, "artist": artist, "album": "",
                                "duration": dur, "sources": sources})
    try:
        return json.loads(urllib.request.urlopen(
            "http://go-adapter:8811/resolve?" + q, timeout=120).read())
    except Exception as e:
        return {"error": str(e)}


for name, artist, album, dur in SONGS:
    d = resolve(name, artist, dur)
    print("=" * 72)
    print("目标: %s / %s (%s秒)" % (name, artist, dur))
    for o in (d.get("outcomes") or []):
        cands = o.get("candidates") or []
        print("  来源 %-8s 匹配=%s 候选 %d 个" % (o.get("source"), o.get("matched"), len(cands)))
        for c in cands[:4]:
            print("      %-26s %-18s %s秒" % (str(c.get("name"))[:24],
                                               str(c.get("artist"))[:16], c.get("duration")))
