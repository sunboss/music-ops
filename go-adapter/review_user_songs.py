"""
复盘用户手机上实际播放过的曲目：这些 id 来自手机回报的音频地址，
其中 3368415348 / 18637990 播了 30 秒，1329840961 播了 45 秒（均为网易云外链试听）。
逐首走完整链路，看现在能否拿到完整音源。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"
IDS = ["3368415348", "18637990", "1329840961", "2160200175", "1352916750", "3345742920",
       "1964850580", "4872687"]


def jget(path, timeout=180):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


print("%-14s %-18s %-9s %-10s %-9s %s" % ("歌曲ID", "歌名", "歌曲时长", "外链大小", "文件时长", "结论"))
print("-" * 88)
ok = clip = none = 0
for sid in IDS:
    name, artist, album, dur = server.song_detail(sid)
    osz = server.measure_size(server.NETEASE_OUTER + urllib.parse.quote(sid))
    note = "(外链 %dKB)" % (osz // 1024) if osz else "(外链无)"
    try:
        u = jget("/api/song/url?id=%s" % sid)
        it = (u.get("data") or [{}])[0]
        url = it.get("url")
        src = it.get("source") or "-"
        if not url:
            none += 1
            print("%-14s %-18s %-9s %-10s %-9s %s" % (sid, name[:16], dur, note, "-", "无音源(如实报错)"))
            continue
        with urllib.request.urlopen(url if url.startswith("http") else BASE + url, timeout=180) as r:
            body = r.read()
        open("/tmp/rev.bin", "wb").write(body)
        actual = server.probe_duration("/tmp/rev.bin")
        if dur and actual and actual < dur - 8:
            clip += 1
            verdict = "★ 仍是片段"
        else:
            ok += 1
            verdict = "完整 (%s)" % src
        print("%-14s %-18s %-9s %-10s %-9s %s" % (sid, name[:16], dur, note, round(actual, 1), verdict))
    except Exception as e:
        print("%-14s %-18s %-9s %-10s %-9s %s" % (sid, name[:16], dur, note, "-", "异常:" + str(e)[:24]))

print()
print("完整 %d 首 / 无音源 %d 首 / 仍是片段 %d 首" % (ok, none, clip))
