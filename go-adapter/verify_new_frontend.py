#!/usr/bin/env python3
"""新前端 P0 验收：三档宽度 + 关键页面截图"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9440
BASE = "http://127.0.0.1:5199"
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
os.makedirs(OUT, exist_ok=True)

prof = tempfile.mkdtemp(prefix="rm-new-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--autoplay-policy=no-user-gesture-required",
                         "--remote-allow-origins=*", "--window-size=1440,900", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws_url = None
for _ in range(40):
    try:
        for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
            if t.get("type") == "page":
                ws_url = t["webSocketDebuggerUrl"]; break
        if ws_url: break
    except Exception: pass
    time.sleep(0.5)
ws = websocket.create_connection(ws_url, timeout=120, max_size=64 * 1024 * 1024)
n = [0]
errors = []


def cmd(m, **p):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]:
            return r.get("result", {})


def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r:
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:160]
    return r.get("result", {}).get("value")


def go(path, w, h, wait=6, hold=None):
    cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if w < 700 else 1,
        mobile=w < 700)
    cmd("Page.navigate", url=BASE + path)
    time.sleep(wait)
    # 轮询等待内容就绪，避免截到骨架态
    if hold:
        for _ in range(30):
            if ev(hold):
                time.sleep(1.5)
                break
            time.sleep(2)


def shot(name):
    d = cmd("Page.captureScreenshot", format="png")
    p = os.path.join(OUT, name)
    with open(p, "wb") as f:
        f.write(base64.b64decode(d["data"]))
    print("   ", name)


try:
    cmd("Page.enable")
    cmd("Runtime.enable")
    cmd("Log.enable")

    for w, h, tag in [(1440, 900, "1440"), (768, 1024, "768"), (390, 844, "390")]:
        go("/", w, h, 6, hold="document.querySelectorAll('.card').length>3")
        print("首页 %s -> 标题=%r 卡片=%s 横向溢出=%s" % (
            tag, (ev("document.querySelector('h1')?.textContent") or "")[:24],
            ev("document.querySelectorAll('.card').length"),
            ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth")))
        shot("new-home-%s.png" % tag)

    go("/playlist/24381616", 1440, 900, 6, hold="document.querySelector('h1')?.textContent")
    print("歌单@1440 -> 曲目行=%s 标题=%r" % (
        ev("document.querySelectorAll('.row').length"),
        (ev("document.querySelector('h1')?.textContent") or "")[:30]))
    shot("new-playlist-1440.png")

    go("/playlist/24381616", 390, 844, 6, hold="document.querySelectorAll('.row').length>5")
    print("歌单@390 -> 横向溢出=%s 迷你条=%s 底部Tab=%s" % (
        ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"),
        ev("!!document.querySelector('.mini, [class*=mini]')"),
        ev("!!document.querySelector('nav')")))
    shot("new-playlist-390.png")

    go("/ai", 390, 844, 6)
    print("AI@390 -> 输入框=%s 场景按钮=%s" % (
        ev("!!document.querySelector('input')"), ev("document.querySelectorAll('.chips button').length")))
    shot("new-ai-390.png")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
