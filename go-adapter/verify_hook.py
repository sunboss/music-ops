#!/usr/bin/env python3
"""验证取源监控：在站点页面里发起一次 /song/url 请求，看服务端能否收到回报"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9423

prof = tempfile.mkdtemp(prefix="rm-hook-")
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
        return "抛错:" + str(r["exceptionDetails"])[:150]
    return r.get("result", {}).get("value")


try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(10)
    print("注入版本:", ev("window.__RM_VERSION"))
    print("监控已装载:", ev("typeof window.__rmReport === 'function'"))
    print("发起一次 /song/url 请求（模拟播放器取源）…")
    print("响应:", str(ev("fetch('/api/song/url?id=4872687&br=320000').then(r=>r.text()).then(t=>t.slice(0,150))"))[:150])
    time.sleep(4)
finally:
    try:
        ws.close()
    except Exception:
        pass
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
