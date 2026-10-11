import json
import time
import urllib.request

BASE = "http://127.0.0.1:3001"


def g(u, t=180):
    return urllib.request.urlopen(u, timeout=t).read().decode()


CASES = [
    ("186016", "晴天 / 周杰伦"),
    ("1901371647", "孤勇者 / 陈奕迅"),
    ("1495784715", "给电影人的情书 / 单依纯"),
]

print("== /api/song/url 换源链路")
ok = 0
for sid, label in CASES:
    t0 = time.time()
    try:
        d = json.loads(g(BASE + "/api/song/url?id=" + sid))
    except Exception as e:
        print("  %s: 请求失败 %s" % (label, e))
        continue
    it = (d.get("data") or [{}])[0]
    has = bool(it.get("url"))
    if has:
        ok += 1
    print("  %s -> url=%s size=%s br=%s 用时=%.1fs"
          % (label, "有" if has else "无", it.get("size"), it.get("br"), time.time() - t0))

print("== 音频代理 Range 检查")
sid = CASES[0][0]
req = urllib.request.Request(BASE + "/api/audio/proxy?id=" + sid,
                             headers={"Range": "bytes=0-1023"})
with urllib.request.urlopen(req, timeout=60) as r:
    body = r.read()
    print("  状态=%s Content-Range=%s 收到=%d 字节"
          % (r.status, r.headers.get("Content-Range"), len(body)))

print("== 缓存命中速度")
t0 = time.time()
d = json.loads(g(BASE + "/api/song/url?id=" + sid))
it = (d.get("data") or [{}])[0]
print("  二次请求 size=%s br=%s 用时=%.2fs" % (it.get("size"), it.get("br"), time.time() - t0))
print("== 汇总: %d/%d 换源成功" % (ok, len(CASES)))
