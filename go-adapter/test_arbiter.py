"""对照实验：规则匹配失败、大模型终审能救回的案例
重点测规则**永远做不到**的部分：歌手别名/英文名/组合写法、歌名括号补充"""
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import server  # noqa: E402

CASES = [
    ("晴天", "Jay Chou", 269, "英文名 vs 中文名(周杰伦)"),
    ("十年", "Eason Chan", 205, "英文名 vs 中文名(陈奕迅)"),
    ("海阔天空", "Beyond", 240, "对照：本来就能严格匹配"),
    ("富士山下", "Eason Chan", 259, "英文名 vs 中文名"),
    ("光辉岁月", "BEYOND", 299, "大小写 + 乐队写法"),
    ("爱在西元前", "Jay Chou", 234, "英文名 vs 中文名"),
    ("红豆", "Faye Wong", 259, "英文名 vs 中文名(王菲)"),
]


def strict(name, artist, dur, src="kuwo"):
    q = urllib.parse.urlencode({"name": name, "artist": artist, "album": "",
                                "duration": dur, "source": src})
    try:
        r = json.loads(urllib.request.urlopen(
            server.GO_ADAPTER + "/resolve-url?" + q, timeout=80).read())
        return (r.get("song") or {}), True
    except Exception:
        return None, False


import json  # noqa: E402

print("%-22s %-8s %-8s %s" % ("案例", "规则", "大模型", "命中结果"))
print("-" * 78)
rec = 0
for name, artist, dur, note in CASES:
    s1, ok1 = strict(name, artist, dur)
    s2 = server.ai_pick_source(name, artist, "", dur)
    if s2:
        rec += 1
    print("%-22s %-8s %-8s %s" % (
        (name + "/" + artist)[:20], "✔" if ok1 else "✘", "✔" if s2 else "✘",
        ("%s / %s / %s秒" % ((s2 or {}).get("song", {}).get("name"),
                             (s2 or {}).get("song", {}).get("artist"),
                             (s2 or {}).get("song", {}).get("duration")))
        if s2 else (note if not ok1 else "（规则已命中）")))
print("-" * 78)
print("规则失败、大模型救回: %d / %d" % (rec, len(CASES)))
