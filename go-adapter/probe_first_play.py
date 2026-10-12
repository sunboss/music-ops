"""首播耗时拆解：连接复用前 vs 后"""
import glob
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/app")
import server  # noqa: E402

SID = "4872687"
c = sqlite3.connect(server.CACHE_DB)
c.execute("DELETE FROM url_cache WHERE song_id=?", (SID,))
c.commit()
c.close()
for f in glob.glob(os.path.join(server.AUDIO_DIR, SID + ".*")):
    os.remove(f)

t0 = time.time()
t = time.time()
n, a, al, dur = server.song_detail(SID)
print("  取元数据        %6.0f ms" % ((time.time() - t) * 1000))
t = time.time()
res = server.go_resolve(n, a, al, dur)
print("  换源取链(首次)   %6.0f ms" % ((time.time() - t) * 1000))
t = time.time()
res = server.go_resolve(n, a, al, dur)
print("  换源取链(连接复用) %6.0f ms" % ((time.time() - t) * 1000))
t = time.time()
lp, why = server.fetch_to_disk(SID, res["url"], dur)
print("  下载+解码校验    %6.0f ms  (%s)" % ((time.time() - t) * 1000, why))
print("  首播合计        %6.0f ms" % ((time.time() - t0) * 1000))
