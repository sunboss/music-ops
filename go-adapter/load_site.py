#!/usr/bin/env python3
"""加载站点首页（真实 Chrome），用于验证客户端回报链路是否通畅"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9422

prof = tempfile.mkdtemp(prefix="rm-load-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run",
                         "--autoplay-policy=no-user-gesture-required", "--mute-audio",
                         "--window-size=1280,900", "--remote-allow-origins=*", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws_url = None
for _ in range(40):
    try:
        for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
            if t.get("type") == "page":
                ws_url = t["webSocketDebuggerUrl"]
                break
        if ws_url:
            break
    except Exception:
        pass
    time.sleep(0.5)

ws = websocket.create_connection(ws_url, timeout=60, max_size=64 * 1024 * 1024)
n = [0]


def cmd(method, **params):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == n[0]:
            return m.get("result", {})


def ev(expr):
    r = cmd("Runtime.evaluate", expression=expr, returnByValue=True)
    return r.get("result", {}).get("value")


try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    print("已打开站点，等待回报…")
    time.sleep(12)
    print("注入版本:", ev("window.__RM_VERSION"))
    print("SW 注册数:", ev("navigator.serviceWorker ? 'has-api' : 'no-api'"))
    print("播放条存在:", ev("!!document.querySelector('.player')"))
finally:
    try:
        ws.close()
    except Exception:
        pass
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
