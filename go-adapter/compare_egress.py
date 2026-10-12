"""
决定性实验：同一个上游直链，对比「东京直连」与「经 Go 服务走国内出口」拿到的文件。
若两者时长/体积不同 —— 说明国内平台对海外 IP 只给短片段，音频抓取也必须走国内。
"""
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

SONGS = ["4872687", "186016", "1901371647", "436514312"]


def probe(data, tag):
    p = "/tmp/cmp_%s.bin" % tag
    with open(p, "wb") as f:
        f.write(data)
    return len(data), round(server.probe_duration(p), 1)


print("%-10s %-16s %-18s %-18s %s" % ("歌曲", "上游直链主机", "东京直连", "经国内出口", "是否相同"))
print("-" * 92)
for sid in SONGS:
    name, artist, album, dur = server.song_detail(sid)
    off, _ = server.official_url(sid)
    up = off
    src_tag = "官方"
    if not up:
        r = server.go_resolve(name, artist, album, dur)
        up = (r or {}).get("url")
        src_tag = "换源"
    if not server.is_http(up):
        print("%-10s 取不到直链" % (name[:8]))
        continue
    host = urllib.parse.urlparse(up).netloc

    # A) 东京直连
    try:
        req = urllib.request.Request(up, headers={"User-Agent": server.UA_BROWSER})
        with urllib.request.urlopen(req, timeout=120) as r:
            a = r.read()
        sa, da = probe(a, "direct")
    except Exception as e:
        sa, da = -1, str(e)[:20]

    # B) 经 Go 服务（国内出口）
    try:
        via = server.GO_ADAPTER + "/fetch?url=" + urllib.parse.quote(up, safe="")
        with urllib.request.urlopen(via, timeout=300) as r:
            b = r.read()
        sb, db = probe(b, "vg")
    except Exception as e:
        sb, db = -1, str(e)[:20]

    same = (sa == sb)
    print("%-10s %-16s %-18s %-18s %s" % (
        name[:8], host[:14],
        "%s字节/%.1fs" % (sa, da) if sa >= 0 else "失败",
        "%s字节/%.1fs" % (sb, db) if sb >= 0 else ("失败: %s" % db),
        "相同" if same else "★ 不同！"))
