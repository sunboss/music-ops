#!/usr/bin/env python3
"""用真实 Chrome 加载站点上的播放诊断页，读回结果（端到端：Cloudflare + 我们的代理 + 浏览器解码）"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9420
SID = sys.argv[1] if len(sys.argv) > 1 else "4872687"
URL = "https://music.1234r.com/diag.html?id=" + SID

prof = tempfile.mkdtemp(prefix="rm-diag-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
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
    if "exceptionDetails" in r:
        return "抛错: " + str(r["exceptionDetails"])[:120]
    return r.get("result", {}).get("value")


try:
    cmd("Page.enable")
    print("打开诊断页:", URL)
    cmd("Page.navigate", url=URL + "&_=" + str(int(time.time())))
    for i in range(10):
        time.sleep(3)
        txt = ev("(document.getElementById('out')||{}).innerText")
        if txt and ("结论" in txt or "出错" in txt):
            print("\n--- 诊断页结果 ---")
            print(txt)
            break
        if i == 9:
            print("超时，当前页面文本:", (txt or "")[:300])
    print()
    print("浏览器里的音频元素:", ev("""(() => { const a=document.getElementById('a');
        return a ? JSON.stringify({src:(a.src||'').slice(-60), dur:a.duration, t:a.currentTime,
                                   paused:a.paused, ready:a.readyState}) : '无'; })()"""))
finally:
    try:
        ws.close()
    except Exception:
        pass
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
