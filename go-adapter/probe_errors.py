"""查看 kugou/qq/migu 取直链失败的具体原因"""
import json
import urllib.error
import urllib.parse
import urllib.request

ADAPTER = "http://go-adapter:8811"


def call(path, **kw):
    u = ADAPTER + path + "?" + urllib.parse.urlencode(kw)
    try:
        with urllib.request.urlopen(u, timeout=45) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"raw": "非 JSON"}
    except Exception as e:
        return 0, {"error": str(e)}


for src in ["kugou", "qq", "migu"]:
    st, d = call("/resolve-url", name="晴天", artist="周杰伦", duration="269", source=src)
    print("=== %s /resolve-url -> HTTP %s" % (src, st))
    print("    %s" % json.dumps({k: v for k, v in d.items() if k != "song"}, ensure_ascii=False)[:400])
    if d.get("song"):
        s = d["song"]
        print("    命中: %r / %r / %ss" % (s.get("name"), s.get("artist"), s.get("duration")))
    print()

print("=== 适配器整体 /resolve-best（kuwo, kugou, qq, migu）")
st, d = call("/resolve-best", name="晴天", artist="周杰伦", duration="269",
             sources="kugou,qq,migu,kuwo")
print("HTTP %s status=%s url=%s" % (st, d.get("status"), (d.get("url") or "")[:80]))
for a in d.get("attempts") or []:
    print("   %-8s %s %s" % (a.get("source"), a.get("status"), (a.get("error") or "")[:150]))
