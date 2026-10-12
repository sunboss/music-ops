"""复测：以前判为「无完整音源」的歌，AI 选源能救回几首"""
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

SONGS = [("3368415348", "孤独Person"), ("1329840961", "想你和我们的以后"),
         ("2747925048", "Dear D"), ("3347295437", "失眠了"), ("3399839173", "甲乙丙丁"),
         ("4872687", "同花顺(对照,应已有源)")]

for sid, label in SONGS:
    t0 = time.time()
    try:
        req = urllib.request.Request("http://127.0.0.1:3001/api/audio/proxy?id=" + sid)
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
        open("/tmp/audio.bin", "wb").write(data)
        dur = server.probe_duration("/tmp/audio.bin")
        print("  %-18s %s -> HTTP 200, %d 字节, 实测 %s 秒, 耗时 %.0f 秒"
              % (label, sid, len(data), ("%.1f" % dur) if dur else "解不出", time.time() - t0),
              flush=True)
    except urllib.error.HTTPError as e:
        print("  %-18s %s -> HTTP %s (无音源), 耗时 %.0f 秒"
              % (label, sid, e.code, time.time() - t0), flush=True)
    except Exception as e:
        print("  %-18s %s -> 异常 %s" % (label, sid, str(e)[:70]), flush=True)
