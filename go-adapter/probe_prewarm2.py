"""用可播的歌验证预热效果：列表加载后，第一首应该很快落盘"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

KW = "富士山下"          # 陈奕迅，确认可播
u = "http://127.0.0.1:3001/api/search?keywords=%s&type=1&limit=10" % urllib.parse.quote(KW) \
    if False else "http://127.0.0.1:3001/api/search?keywords=%E5%AF%8C%E5%A3%AB%E5%B1%B1%E4%B8%8B&type=1&limit=10"

ids = server.collect_song_ids(json.loads(urllib.request.urlopen(u, timeout=40).read()), 5)
print("列表前几个 id:", ids)

t0 = time.time()
ok = None
for _ in range(25):
    time.sleep(2)
    for i in ids[:2]:
        if server.audio_cached(i):
            ok = i
            break
    if ok:
        break
if ok:
    print("✔ 预热 %s 在 %.0f 秒内落盘 -> 用户点它时无需等待下载" % (ok, time.time() - t0))
    print("   实测时长:", server.probe_duration(server.audio_cached(ok)))
else:
    print("✘ 预热未落盘（可能前两首都取不到源）")

print("\n=== 对照：未预热的歌首次播放要多久")
for i in ids[2:5]:
    if server.audio_cached(i):
        continue
    t = time.time()
    try:
        urllib.request.urlopen("http://127.0.0.1:3001/api/audio/proxy?id=" + i, timeout=120).read()
        print("   %s 首次播放 %.0f 毫秒" % (i, (time.time() - t) * 1000))
    except Exception as e:
        print("   %s 失败 %s" % (i, str(e)[:50]))
    break
