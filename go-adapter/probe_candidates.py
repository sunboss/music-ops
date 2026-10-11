"""查看各来源的候选与拒绝原因，判断是“真不匹配”还是“匹配过严”"""
import json
import urllib.error
import urllib.parse
import urllib.request

ADAPTER = "http://go-adapter:8811"


def resolve(name, artist, dur, src):
    q = urllib.parse.urlencode({"name": name, "artist": artist, "duration": str(dur), "sources": src})
    try:
        with urllib.request.urlopen(ADAPTER + "/resolve?" + q, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())
    except Exception as e:
        return {"error": str(e)}


for src in ["migu", "soda", "fivesing", "qianqian", "kugou", "qq"]:
    d = resolve("晴天", "周杰伦", 269, src)
    oc = (d.get("outcomes") or [{}])[0]
    print("=== %s 状态=%s 错误=%s" % (src, oc.get("status"), (oc.get("error") or "")[:60]))
    for c in (oc.get("candidates") or [])[:5]:
        print("    候选: %r | %r | %ss | album=%r" % (c.get("name"), c.get("artist"),
                                                     c.get("duration"), (c.get("album") or "")[:20]))
    print("    拒绝原因: %s" % (oc.get("rejected") or [])[:4])
    print()
