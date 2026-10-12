#!/usr/bin/env python3
"""音源平台巡检：逐平台实测（2 首样本），可用→不可用即告警。
输出写 /data/sunboss/music/data/source_health.json + 日志；状态变化时打印 [ALERT]。
在东京容器内运行：docker exec music-enhancer python3 /app/check_sources.py --once
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

GO = os.getenv("GO_ADAPTER", "http://172.19.0.1:18811")
DB = "/data/source_health.json"
HIST = "/data/source_health.log"
SAMPLES = [("晴天", "周杰伦", 269), ("Shape of You", "Ed Sheeran", 233)]
# migu 之前 30s 超时已摘除主链，但仍巡检以便决定要不要恢复
SOURCES = ["kuwo", "kugou", "qq", "netease", "qianqian", "bilibili", "joox", "soda",
           "fivesing", "jamendo", "migu"]
TIMEOUT = 45
MIN_OK = 1          # 2 首里至少 1 首出直链才算可用


def probe(src, name, artist, dur):
    """/resolve-best 有直链 200 + url；无直链 404（正常业务态，不是故障）"""
    q = urllib.parse.urlencode({"name": name, "artist": artist, "duration": dur, "sources": src})
    t0 = time.time()
    try:
        with urllib.request.urlopen(GO + "/resolve-best?" + q, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        url = (d or {}).get("url") or ""
        if url.startswith("http"):
            req = urllib.request.Request(url, headers={"Range": "bytes=0-1"})
            with urllib.request.urlopen(req, timeout=25) as r2:
                ok = r2.status in (200, 206)
        else:
            ok = False
    except urllib.error.HTTPError as e:
        return False, round(time.time() - t0, 1), ("无直链" if e.code == 404 else "HTTP %d" % e.code)
    except Exception as e:
        return False, round(time.time() - t0, 1), str(e)[:50]
    return ok, round(time.time() - t0, 1), ""


def run_once():
    prev = {}
    try:
        with open(DB) as f:
            prev = json.load(f)
    except Exception:
        pass
    health = {}
    for s in SOURCES:
        wins = 0
        cost = 0.0
        err = ""
        for name, artist, dur in SAMPLES:
            ok, t, e = probe(s, name, artist, dur)
            cost = max(cost, t)
            if ok:
                wins += 1
            elif e:
                err = e
        health[s] = {"ok": wins >= MIN_OK, "wins": wins, "cost_s": cost, "err": err,
                     "ts": time.time()}
        was = prev.get(s, {}).get("ok")
        mark = ""
        if was is True and not health[s]["ok"]:
            mark = "  [ALERT] %s 从可用 -> 不可用!" % s
        elif was is False and health[s]["ok"]:
            mark = "  [RECOVER] %s 恢复可用" % s
        print("%-10s %s  %2d/2 直链  最慢 %.1fs  %s%s"
              % (s, "OK " if health[s]["ok"] else "BAD", wins, cost, err, mark))
    with open(DB, "w") as f:
        json.dump(health, f, ensure_ascii=False, indent=1)
    with open(HIST, "a") as f:
        f.write(time.strftime("%F %T") + " " +
                " ".join("%s=%s" % (k, "1" if v["ok"] else "0") for k, v in health.items()) + "\n")
    # watchdog 约定：一切正常就保持安静（stdout 为空 = 不投递）；只有异常/恢复才出声
    alerts = [s for s, v in health.items()
              if s in prev and prev[s].get("ok") != v["ok"]]
    if alerts:
        for s in alerts:
            print("[状态变化] %s: %s -> %s" % (s, "可用" if prev[s].get("ok") else "不可用",
                                               "可用" if health[s]["ok"] else "不可用"))


if __name__ == "__main__":
    run_once()
