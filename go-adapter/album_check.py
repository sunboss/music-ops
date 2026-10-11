"""
逐首体检指定专辑：每首走完整链路（取源 -> 落盘 -> 解码真实时长），与歌曲时长比对。
用于复盘用户实际在听的专辑/歌单里是否存在「时长不符」的曲目。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

BASE = "http://127.0.0.1:3001"
SONG_HINT = sys.argv[1] if len(sys.argv) > 1 else "4872687"


def jget(path, timeout=180):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# 先通过一首已知歌曲找到它所属专辑
d = jget("/api/song/detail?ids=%s" % SONG_HINT)
song = (d.get("songs") or [{}])[0]
al = song.get("al") or {}
album_id = al.get("id")
print("专辑: %s (id=%s)" % (al.get("name"), album_id))

tracks = []
try:
    a = jget("/api/album?id=%s" % album_id)
    for s in (a.get("songs") or []):
        tracks.append((str(s.get("id")), s.get("name", ""), round((s.get("dt") or 0) / 1000.0, 1)))
except Exception as e:
    print("取专辑失败:", str(e)[:60])

print("曲目数:", len(tracks))
print()
print("%-26s %-9s %-9s %-10s %s" % ("曲目", "歌曲时长", "文件时长", "判定", "来源"))
print("-" * 76)
bad, ok, none_cnt = [], 0, 0
for sid, name, dt in tracks:
    try:
        u = jget("/api/song/url?id=%s" % sid)
        it = (u.get("data") or [{}])[0]
        url = it.get("url")
        if not url:
            none_cnt += 1
            print("%-26s %-9s %-9s %-10s %s" % (name[:24], dt, "-", "无音源", "-"))
            continue
        with urllib.request.urlopen(url if url.startswith("http") else BASE + url, timeout=180) as r:
            body = r.read()
        open("/tmp/alb.bin", "wb").write(body)
        actual = server.probe_duration("/tmp/alb.bin")
        src = it.get("source") or "-"
        if dt and actual and actual < dt - 8:
            verdict = "★ 时长不符"
            bad.append((name, dt, round(actual, 1), src))
        else:
            verdict = "完整"
            ok += 1
        print("%-26s %-9s %-9s %-10s %s" % (name[:24], dt, round(actual, 1), verdict, src))
    except Exception as e:
        print("%-26s %-9s %-9s %-10s %s" % (name[:24], dt, "-", "异常", str(e)[:30]))

print()
print("完整 %d 首 / 无音源 %d 首 / 时长不符 %d 首" % (ok, none_cnt, len(bad)))
for b in bad:
    print("   不符:", b)
