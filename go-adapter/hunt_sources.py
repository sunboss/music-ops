"""
对「取不到完整音源」的曲目做多来源穷举：逐个来源严格匹配 + 实际下载 + 解码时长，
看是否有任何来源能提供完整音频。结果用于决定是否扩充 FALLBACK_SOURCES。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

ADAPTER = server.GO_ADAPTER
SOURCES = ["kuwo", "kugou", "qq", "migu", "bilibili", "qianqian", "soda", "fivesing", "netease"]
SONGS = ["3368415348", "1329840961", "2747925048", "3347295437", "3399839173"]


def jget(url, timeout=180):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def dur_of(url):
    req = urllib.request.Request(url, headers={"User-Agent": server.UA_BROWSER})
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read()
    p = "/tmp/ms.bin"
    with open(p, "wb") as f:
        f.write(body)
    return len(body), round(server.probe_duration(p), 1)


for sid in SONGS:
    name, artist, album, dur = server.song_detail(sid)
    print("=== %s / %s  期望 %s 秒  (id=%s 专辑=%s)" % (name, artist, dur, sid, (album or "")[:26]))
    for src in SOURCES:
        q = urllib.parse.urlencode({"name": name, "artist": artist, "duration": str(dur),
                                    "source": src})
        try:
            d = jget(ADAPTER + "/resolve-url?" + q, timeout=90)
            u = d.get("url")
            if not server.is_http(u):
                print("   %-9s 无匹配" % src)
                continue
            size, actual = dur_of(u)
            ok = bool(dur) and actual >= dur - 8
            print("   %-9s %s %d字节/%s秒 %s" % (src, "★完整" if ok else "片段 ", size, actual,
                                               "" if ok else "(拒绝)"))
        except urllib.error.HTTPError as e:
            try:
                b = json.loads(e.read().decode())
                print("   %-9s %s" % (src, (b.get("error") or "")[:60]))
            except Exception:
                print("   %-9s HTTP %s" % (src, e.code))
        except Exception as e:
            print("   %-9s 异常 %s" % (src, str(e)[:50]))
    print()
