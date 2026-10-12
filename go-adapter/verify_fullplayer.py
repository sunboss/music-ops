#!/usr/bin/env python3
"""验收全屏播放器：播放 -> 打开全屏 -> 歌词高亮 -> 拖动进度"""
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
PORT = 9443
BASE = "http://127.0.0.1:5199"
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
prof = tempfile.mkdtemp(prefix="rm-fp-")
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


def shot(name):
    d = cmd("Page.captureScreenshot", format="png")
    open(os.path.join(OUT, name), "wb").write(base64.b64decode(d["data"]))


def wait_for(expr, secs=45):
    for _ in range(secs):
        if ev(expr):
            return True
        time.sleep(1)
    return False


try:
    cmd("Page.enable")
    # 桌面
    cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
    cmd("Page.navigate", url=BASE + "/playlist/24381616")
    wait_for("document.querySelectorAll('.row').length>5")
    print("歌单已加载，行数:", ev("document.querySelectorAll('.row').length"))
    ev("document.querySelectorAll('.row')[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2})); 'ok'")
    print("已双击播放第一首")
    if wait_for("!!document.querySelector('.mini') && !!document.querySelector('.bar .pc img')", 45):
        print("播放条出现 ✓（迷你条 + 播放条封面均已渲染）")
    else:
        print("播放条未出现：mini=%s pc-img=%s" % (
            ev("!!document.querySelector('.mini')"), ev("!!document.querySelector('.bar .pc img')")))
    time.sleep(3)
    print("播放状态:", ev("document.getElementById('app').__vue_app__ ? 'n/a' : 'n/a'"))
    # 打开全屏播放器（桌面点播放条封面）
    ev("document.querySelector('.bar .pc').click(); 'ok'")
    ok = wait_for("!!document.querySelector('.fp')", 10)
    print("全屏播放器打开:", ok)
    time.sleep(6)
    print("  当前曲:", ev("document.querySelector('.fp .nm')?.textContent"))
    print("  歌词行数:", ev("document.querySelectorAll('.fp .ln').length"))
    print("  高亮行:", ev("document.querySelector('.fp .ln.on')?.textContent?.slice(0,30)"))
    print("  进度:", ev("document.querySelector('.fp .times')?.textContent"))
    shot("fullplayer-desktop.png")

    # 拖动进度到 50%，看歌词是否跟随
    ev("""(function(){var t=document.querySelector('.fp .track');var r=t.getBoundingClientRect();
        t.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:r.left+r.width*0.5,clientY:r.top+2}));return 'ok';})()""")
    time.sleep(4)
    print("  拖到 50% 后 -> 进度:", ev("document.querySelector('.fp .times')?.textContent"),
          "| 高亮行:", ev("document.querySelector('.fp .ln.on')?.textContent?.slice(0,26)"))
    shot("fullplayer-desktop-seek.png")

    # 移动端
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    time.sleep(3)
    print("\n移动端全屏:", ev("!!document.querySelector('.fp')"),
          "| 视口溢出:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"))
    shot("fullplayer-mobile.png")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
