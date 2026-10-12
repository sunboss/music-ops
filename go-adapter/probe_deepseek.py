"""DeepSeek 切换后，验证另外两处 AI 能力"""
import json
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

print("当前模型:", server.AI_MODEL, "| 备用:", server.AI_MODEL_FALLBACKS)
print("网关:", server.AI_GATEWAY)

print("\n=== 1) 搜索词归属（后台大模型）：清缓存后重算")
c = sqlite3.connect(server.CACHE_DB)
c.execute("DELETE FROM search_artist WHERE q='晴天'")
c.commit()
c.close()
print("   清掉了「晴天」的缓存，直接问一次：")
server._bg_search_artist("晴天")
print("   结果:", server.search_artist_cached("晴天"))

print("\n=== 2) AI 终审选源（规则做不到的跨语言歌手）")
for name, artist, dur in [("晴天", "Jay Chou", 269), ("红豆", "Faye Wong", 259)]:
    t = time.time()
    r = server.ai_pick_source(name, artist, "", dur)
    s = (r or {}).get("song") or {}
    print("   %s / %s -> %s  耗时 %.1f 秒" % (
        name, artist,
        ("✔ %s / %s / %s秒 (%s)" % (s.get("name"), s.get("artist"), s.get("duration"),
                                    r.get("reason", "")[:30])) if r else "✘ 未救回",
        time.time() - t))
