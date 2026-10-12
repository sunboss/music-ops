"""验证 /api/search 与搜索补原唱"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

B = "http://127.0.0.1:3001"


def show(path, label):
    url = B + path
    try:
        r = urllib.request.urlopen(url, timeout=30)
        body = r.read()
        print("%s -> HTTP %s, %d 字节" % (label, r.status, len(body)))
        d = json.loads(body)
        for i, s in enumerate(((d.get("result") or {}).get("songs") or [])[:5]):
            ar = "/".join(a.get("name", "") for a in (s.get("ar") or []))
            print("     %d. %s / %s" % (i + 1, s.get("name"), ar))
    except Exception as e:
        print("%s -> 异常 %s" % (label, str(e)[:120]))


print("=== 缓存里的搜索词归属")
print("   ", server.search_artist_cached("晴天"))

print("\n=== /api/search 第一次（会后台问大模型）")
show("/api/search?keywords=%E6%99%B4%E5%A4%A9&type=1&limit=5", "  /api/search")

print("\n=== 等待后台大模型判定")
for _ in range(10):
    time.sleep(2)
    ent = server.search_artist_cached("晴天")
    if ent is not None:
        break
print("    缓存结果:", ent)

print("\n=== /api/search 第二次（应把原唱放到最前）")
show("/api/search?keywords=%E6%99%B4%E5%A4%A9&type=1&limit=5", "  /api/search")

print("\n=== 对照 /api/cloudsearch")
show("/api/cloudsearch?keywords=%E6%99%B4%E5%A4%A9&type=1&limit=5", "  /api/cloudsearch")
