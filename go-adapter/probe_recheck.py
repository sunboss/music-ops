"""验证：缓存淘汰 与 无音源主动复核"""
import sys
import time

sys.path.insert(0, "/app")
import server  # noqa: E402

print("=== 1) 缓存与磁盘现状")
print("   ", server.audio_cache_stats(), server.disk_usage())

print("\n=== 2) 淘汰：临时把上限压到 20 首，看是否真的删")
orig = server.AUDIO_MAX_FILES
server.AUDIO_MAX_FILES = 20
n = server.evict_audio(force=True)
print("   执行后 files=%d (删除生效=%s)" % (server.audio_cache_stats()["files"], n))
server.AUDIO_MAX_FILES = orig

print("\n=== 3) 复核：把一首已知可播的歌塞进「无音源」登记，看复核能否自动恢复")
sid = "4872687"      # 同花顺，确认可播
server.mark_unplayable(sid)
print("   登记后 is_unplayable =", server.is_unplayable(sid))
# 模拟复核那一刻做的事
server.cache_del(sid)
import sqlite3
c = sqlite3.connect(server.CACHE_DB)
c.execute("DELETE FROM probeable WHERE song_id=?", (sid,))
c.commit()
c.close()
t = time.time()
ok = server.quick_playable(sid)
print("   复核探测 ok=%s（耗时 %.1f 秒）" % (ok, time.time() - t))
if ok:
    server.clear_unplayable(sid)
print("   复核后 is_unplayable =", server.is_unplayable(sid), "-> 恢复显示：", not server.is_unplayable(sid))

print("\n=== 4) 待复核队列（按到期时间）")
print("   ", server.unplayable_expiring(5))
