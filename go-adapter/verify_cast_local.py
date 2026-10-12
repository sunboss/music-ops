#!/usr/bin/env python3
"""验收「本地自动发现」投屏：Chrome 里的能力识别 + DLNA 小桥 → 模拟电视的完整链路"""
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
PORT = 9462
SITE = "https://music.1234r.com"
OUT = "/Users/sunboss/Desktop/AI/music-ops/docs/shots"
prof = tempfile.mkdtemp(prefix="rm-cast2-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required",
                         "--window-size=1440,980", "about:blank"],
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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:180]
    return r.get("result", {}).get("value")


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


def shot(name):
    d = cmd("Page.captureScreenshot", format="jpeg", quality=88)
    open(os.path.join(OUT, name), "wb").write(base64.b64decode(d["data"]))
    return os.path.join(OUT, name)


try:
    cmd("Page.enable")
    cmd("Page.navigate", url=SITE + "/playlist/24381616")
    for _ in range(30):
        time.sleep(2)
        if (ev("document.querySelectorAll('.row').length") or 0) > 0:
            break
    # 起播（行内按钮 hover 才显示，直接派发 dblclick）
    ev("document.querySelector('.row').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))")
    time.sleep(6)
    print("正在播:", ev("""(function(){var st=document.getElementById('app').__vue_app__
        .config.globalProperties.$pinia._s.get('player');return st.queue[st.index]?.name||null;})()"""))

    print("\n=== 这台浏览器的投屏能力识别")
    print("  AirPlay 选择器:", ev("typeof HTMLMediaElement.prototype.webkitShowPlaybackTargetPicker === 'function'"))
    print("  Remote Playback:", ev("'remote' in HTMLMediaElement.prototype"))
    print("  UA 是 Chrome:", ev("/Chrome/.test(navigator.userAgent)"))

    print("\n=== 打开投屏面板")
    print(" ", click(".bar .cast"))
    time.sleep(4)
    print("  各分区标题:", ev("Array.from(document.querySelectorAll('.sheet .ct b')).map(b=>b.textContent).join(' / ')"))
    print("  给 Chrome 的说明:", (ev("document.querySelector('.sheet .card p')?.textContent") or "")[:90].replace("\n", " "))
    print("  DLNA 段落文案:", (ev("Array.from(document.querySelectorAll('.sheet .card p')).map(p=>p.textContent).find(t=>t.includes('DLNA')||t.includes('小桥')||t.includes('渲染器'))") or "")[:80])
    print("  发现到的 DLNA 设备:", ev("Array.from(document.querySelectorAll('.sheet .dev b')).map(b=>b.textContent).join(' / ')"))
    print("  截图:", shot("live-cast-local.jpg"))

    print("\n=== 点这台设备 → 小桥 → 模拟电视（完整链路）")
    print(" ", click(".sheet .dev"))
    time.sleep(5)
    print("  面板状态:", (ev("document.querySelector('.sheet .now b')?.textContent") or "(未显示投屏中)"))
    print("  截图:", shot("live-cast-casting.jpg"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
