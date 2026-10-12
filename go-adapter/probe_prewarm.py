"""验证预热与 debug 令牌"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

print("=== 1) debug 接口：带内部令牌")
tok = server.load_internal_token()
print("   令牌已配置:", bool(tok), "长度", len(tok))
req = urllib.request.Request("http://127.0.0.1:3001/api/debug/song?id=186016",
                            headers={"X-RM-Token": tok})
try:
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    print("   带令牌 -> ✔", {k: d.get(k) for k in ("name", "size", "verdict")})
except Exception as e:
    print("   带令牌 -> ✘", str(e)[:80])

print("\n=== 2) 触发一次列表加载（搜索），看是否后台预热")
u = "http://127.0.0.1:3001/api/search?keywords=%E6%99%B4%E5%A4%A9&type=1&limit=10"
d = json.loads(urllib.request.urlopen(u, timeout=40).read())
ids = server.collect_song_ids(d, 5)
print("   列表前几个 id:", ids)
print("   等待后台预热…")
for _ in range(20):
    time.sleep(2)
    done = [i for i in ids if server.audio_cached(i)]
    if done:
        print("   已预热落盘:", done)
        break
for i in ids[:3]:
    print("   %s cached=%s unplayable=%s" % (i, bool(server.audio_cached(i)), server.is_unplayable(i)))
