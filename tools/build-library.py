#!/usr/bin/env python3
"""把「按歌曲 ID 命名的播放缓存」变成「带标签的曲库」。

为什么需要：Music Assistant / Plex / Jellyfin 这类曲库靠**文件内的标签**认歌，
而我们的缓存文件名是 186016.mp3 这种 ID，直接索引出来全是乱名。

做法：
  1. 读缓存里每个 <id>.<ext>
  2. 用网易云（目录层）把 id 换成 标题/歌手/专辑/碟号/年份/封面
  3. 写入标签（MP3→ID3v2，FLAC→Vorbis Comment，M4A→MP4 atoms）+ 嵌入封面
  4. 另存到 data/library/ 下的人类可读文件名（原缓存保持不动，仍按 id 播放）
  5. 生成 library.m3u8 播放清单

用法（容器内）：
  python build_library.py --cache /data/audio_cache --out /data/library --api https://music.1234r.com/api
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    from mutagen import File as MutaFile
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TPE2, TRCK, TDRC, TXXX
    from mutagen.mp4 import MP4, MP4Cover
except ImportError:
    print("需要 mutagen：pip install mutagen")
    sys.exit(2)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def meta_for(api, ids):
    """批量取元数据（网易云目录层）：id -> {title, artist, album, ...}"""
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            d = get_json("%s/song/detail?ids=%s" % (api.rstrip("/"), ",".join(chunk)))
        except Exception as e:
            print("  取元数据失败 %s: %s" % (chunk[:3], str(e)[:60]))
            continue
        for s in (d.get("songs") or []):
            ar = "、".join(a.get("name", "") for a in (s.get("ar") or []) if a.get("name"))
            al = s.get("al") or {}
            out[str(s.get("id"))] = {
                "title": (s.get("name") or "").strip(),
                "artist": ar,
                "album": (al.get("name") or "").strip(),
                "album_artist": (al.get("artist") or {}).get("name") or ar,
                "cover": al.get("picUrl") or "",
                "track": (s.get("no") or 0),
                "year": (al.get("pic_str") or "")[:4] if al.get("pic_str") else "",
                "duration": (s.get("dt") or 0) // 1000,
            }
    return out


def sniff(path):
    """按魔数判断真实容器（上游 Content-Type 会骗人，扩展名不可信）"""
    try:
        with open(path, "rb") as f:
            h = f.read(16)
    except Exception:
        return ""
    if h[:4] == b"fLaC":
        return "flac"
    if h[:4] == b"OggS":
        return "ogg"
    if h[:4] == b"RIFF":
        return "wav"
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf1", b"\xff\xf2"):
        return "mp3"
    if h[4:8] == b"ftyp":
        return "m4a"
    if h[:4] == b"fLaC":
        return "flac"
    return ""


def safe(name, maxlen=90):
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (name or "").strip())
    n = re.sub(r"\s+", " ", n).strip(" .")
    return (n[:maxlen] or "unknown")


def fetch_cover(url):
    if not url:
        return b"", "image/jpeg"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read(), r.headers.get("Content-Type") or "image/jpeg"
    except Exception:
        return b"", "image/jpeg"


def tag_mp3(path, m, cover, ctype):
    try:
        tags = ID3(path)
    except Exception:
        tags = ID3()
    tags.delall("TIT2"); tags.delall("TPE1"); tags.delall("TPE2")
    tags.delall("TALB"); tags.delall("TRCK"); tags.delall("TDRC"); tags.delall("APIC"); tags.delall("TXXX:R-MUSIC")
    tags.add(TIT2(encoding=3, text=m["title"] or "未知"))
    tags.add(TPE1(encoding=3, text=m["artist"] or "未知"))
    tags.add(TPE2(encoding=3, text=m["album_artist"] or m["artist"] or "未知"))
    if m["album"]:
        tags.add(TALB(encoding=3, text=m["album"]))
    if m["track"]:
        tags.add(TRCK(encoding=3, text=str(m["track"])))
    if m["year"]:
        tags.add(TDRC(encoding=3, text=m["year"]))
    tags.add(TXXX(encoding=3, desc="R-MUSIC", text="music.1234r.com"))
    if cover:
        tags.add(APIC(encoding=3, mime=ctype, type=3, desc="Cover", data=cover))
    tags.save(path, v2_version=3)


def tag_flac(path, m, cover, ctype):
    f = FLAC(path)
    f["title"] = m["title"] or "未知"
    f["artist"] = m["artist"] or "未知"
    f["albumartist"] = m["album_artist"] or m["artist"] or "未知"
    if m["album"]:
        f["album"] = m["album"]
    if m["track"]:
        f["tracknumber"] = str(m["track"])
    if m["year"]:
        f["date"] = m["year"]
    f["comment"] = "music.1234r.com"
    f.clear_pictures()
    if cover:
        p = Picture()
        p.type = 3
        p.mime = ctype
        p.desc = "Cover"
        p.data = cover
        f.add_picture(p)
    f.save()


def tag_m4a(path, m, cover, ctype):
    a = MP4(path)
    a["\xa9nam"] = [m["title"] or "未知"]
    a["\xa9ART"] = [m["artist"] or "未知"]
    a["aART"] = [m["album_artist"] or m["artist"] or "未知"]
    if m["album"]:
        a["\xa9alb"] = [m["album"]]
    if m["track"]:
        a["trkn"] = [(int(m["track"]), 0)]
    if m["year"]:
        a["\xa9day"] = [m["year"]]
    if cover:
        a["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_PNG if "png" in ctype else MP4Cover.FORMAT_JPEG)]
    a.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/data/audio_cache")
    ap.add_argument("--out", default="/data/library")
    ap.add_argument("--api", default="https://music.1234r.com/api")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 首（调试用）")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    files = []
    for fn in sorted(os.listdir(a.cache)):
        if fn.endswith(".part") or fn.startswith("."):
            continue
        sid, _, ext = fn.rpartition(".")
        if sid.isdigit():
            files.append((sid, ext.lower(), os.path.join(a.cache, fn)))
    if a.limit:
        files = files[:a.limit]
    print("缓存 %d 个文件，开始生成曲库…" % len(files))

    metas = meta_for(a.api, [f[0] for f in files])
    print("拿到 %d 首的元数据" % len(metas))

    ok, skipped, entries, containers = 0, 0, [], {}
    for sid, ext, path in files:
        m = metas.get(sid)
        if not m or not m["title"]:
            skipped += 1
            print("  跳过（无元数据）%s" % sid)
            continue
        # 以真实容器为准：扩展名与实际不符时（上游 Content-Type 骗人）纠正过来
        real = sniff(path) or ext
        if real != ext:
            containers["%s->%s" % (ext, real)] = containers.get("%s->%s" % (ext, real), 0) + 1
        fname = "%s - %s.%s" % (safe(m["artist"]), safe(m["title"]), real)
        dest = os.path.join(a.out, fname)
        try:
            with open(path, "rb") as s, open(dest, "wb") as d:
                while True:
                    b = s.read(1 << 20)
                    if not b:
                        break
                    d.write(b)
            cover, ctype = fetch_cover(m["cover"])
            if real == "mp3":
                tag_mp3(dest, m, cover, ctype)
            elif real == "flac":
                tag_flac(dest, m, cover, ctype)
            elif real in ("m4a", "mp4"):
                tag_m4a(dest, m, cover, ctype)
            else:
                print("  未识别容器（%s），原样放入：%s" % (real or "?", fname))
            entries.append((int(m["duration"] or 0), m["artist"], m["title"], fname))
            ok += 1
        except Exception as e:
            skipped += 1
            print("  处理失败 %s: %s" % (sid, str(e)[:70]))

    # 写播放清单（Filesystem/多家播放器都能读）
    with open(os.path.join(a.out, "library.m3u8"), "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for dur, ar, ti, fn in sorted(entries, key=lambda x: (x[1], x[2])):
            f.write("#EXTINF:%d,%s - %s\n%s\n" % (dur, ar, ti, fn))

    total = sum(os.path.getsize(os.path.join(a.out, f)) for f in os.listdir(a.out)
                if os.path.isfile(os.path.join(a.out, f)))
    if containers:
        print("扩展名与真实容器不符（已按真实容器纠正）：%s"
              % ", ".join("%s ×%d" % (k, v) for k, v in containers.items()))
    print("完成：带标签 %d 首，跳过 %d 首，曲库 %.0f MB → %s" % (ok, skipped, total / 1048576, a.out))

    # 自检：读回标签并校验时长，避免"写了个空壳"
    for dur, ar, ti, fn in entries[:3]:
        p = os.path.join(a.out, fn)
        f = MutaFile(p)
        got = ""
        if f is not None and f.tags:
            for k in ("TIT2", "\xa9nam", "title"):
                if f.tags.get(k):
                    v = f.tags.get(k)
                    got = str(v.text[0] if hasattr(v, "text") else v[0])
                    break
        print("  自检 %s → 标签标题=%r 时长=%.1fs 字节=%d"
              % (fn[:34], got, f.info.length if f else 0, os.path.getsize(p)))


if __name__ == "__main__":
    main()
