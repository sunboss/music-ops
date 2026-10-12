#!/usr/bin/env python3
"""上线验收：生产域名 https://music.1234r.com 真实浏览器起播、AI、移动端"""
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
PORT = 9456
SITE = "https://music.1234r.com"
OUT = "/Users/sunboss/Desktop/AI/music-ops/docs/shots"
os.makedirs(OUT, exist_ok=True)
prof = tempfile.mkdtemp(prefix="rm-live-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required",
                         "--window-size=1440,900", "about:blank"],
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
ws = websocket.create_connection(ws_url, timeout=180, max_size=64 * 1024 * 1024)
n = [0]


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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:150]
    return r.get("result", {}).get("value")


def dbl(sel, dx=120):
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;e.scrollIntoView({block:'center'});"
           "var r=e.getBoundingClientRect();return JSON.stringify({x:r.left+%d,y:r.top+r.height/2});})()"
           % (sel, dx))
    if not b or b == "null":
        return "无此元素 " + sel
    c = json.loads(b)
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=ct)
        time.sleep(0.06)
    return "已点 " + sel


def click(sel):
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;e.scrollIntoView({block:'center'});"
           "var r=e.getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % sel)
    if not b or b == "null":
        return "无此元素 " + sel
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mouseMoved", x=c["x"], y=c["y"], button="none")
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    return "已点 " + sel


def shot(name, quality=88):
    d = cmd("Page.captureScreenshot", format="jpeg", quality=quality)
    p = os.path.join(OUT, name)
    open(p, "wb").write(base64.b64decode(d["data"]))
    return "%s (%d KB)" % (p, os.path.getsize(p) // 1024)


ST = """(function(){var st=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia._s.get('player');return JSON.stringify({cur:st.queue[st.index]?st.queue[st.index].name:null,
    n:st.queue.length, i:st.index, playing:st.playing, prog:+st.progress.toFixed(1),
    dur:st.duration, err:st.error});})()"""

try:
    cmd("Page.enable")
    print("=== 打开生产站", SITE)
    cmd("Page.navigate", url=SITE)
    time.sleep(9)
    print("  标题:", ev("document.title"), "| 首屏渲染:", ev("!!document.querySelector('.mini, .page')"))
    print("  截图:", shot("live-1-home.jpg"))

    print("\n=== 真实起播（双击首页第一首歌）")
    print(" ", dbl(".grid .card, .row", dx=60))
    for _ in range(40):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["prog"] > 2 and st["playing"]:
            break
    p1 = st["prog"]
    time.sleep(10)
    st2 = json.loads(ev(ST))
    print("  正在播:", st2["cur"], "| 进度 %.1fs -> %.1fs" % (p1, st2["prog"]),
          "✓ 真的在走" if st2["prog"] > p1 + 3 else "✗ 没动")
    print("  音频时长: %.0f 秒 | err=%r" % (st2["dur"], st2["err"]))
    print("  截图:", shot("live-2-playing.jpg"))

    print("\n=== AI 页（生产环境）")
    cmd("Page.navigate", url=SITE + "/ai")
    time.sleep(6)
    print("  标题:", ev("document.querySelector('h1')?.textContent"), "| 无限电台:", json.loads(ev(ST))["n"] >= 0)
    print(" ", click(".chips button"))
    for _ in range(45):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["n"] > 0 and st["playing"]:
            break
    print("  生成歌单:", st["n"], "首 | 正在播:", st["cur"], "| 标签:", ev("document.querySelector('.tag')?.textContent"))
    print("  截图:", shot("live-3-ai.jpg"))

    print("\n=== 移动端 (390x844 iPhone)")
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    cmd("Page.navigate", url=SITE + "/")
    time.sleep(8)
    print("  横向溢出:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"))
    print("  底部导航:", ev("!!document.querySelector('.tabbar, nav')"))
    print("  截图:", shot("live-4-mobile.jpg"))
    print(" ", dbl(".grid .card, .row", dx=40))
    for _ in range(30):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["prog"] > 2:
            break
    print("  手机端起播:", st["cur"], "| 进度 %.1f 秒 ✓" % st["prog"])
    print("  截图:", shot("live-5-mobile-play.jpg"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
