#!/usr/bin/env python3
"""真实浏览器验证口味记忆：用 AI 面板播放 -> 5 秒切歌(应记 skip) -> 听满 35 秒(应记 play)"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9430
prof = tempfile.mkdtemp(prefix="rm-taste2-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--autoplay-policy=no-user-gesture-required",
                         "--remote-allow-origins=*", "--window-size=1280,900", "about:blank"],
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
ws = websocket.create_connection(ws_url, timeout=180, max_size=32 * 1024 * 1024)
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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:120]
    return r.get("result", {}).get("value")


def state():
    return ev("""(function(){var a=document.getElementById('rm-ai-audio');
        return JSON.stringify({src:(a.src||'').slice(-24), t:+(a.currentTime||0).toFixed(1),
        dur:Math.round(a.duration||0), paused:a.paused,
        now:(document.getElementById('rm-ai-now')||{}).textContent||''});})()""")

try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(12)
    print("注入版本:", ev("window.__RM_VERSION"), "| 口味追踪:", ev("!!window.__rmTaste"))
    ev("document.getElementById('rm-ai-btn').click(); 'ok'")

    print("\n--- 用场景按钮生成电台并自动起播")
    ev("""Array.prototype.find.call(document.querySelectorAll('#rm-ai-chips i'),
        function(e){return e.textContent==='开车兜风';}).click(); 'ok'""")
    st = None
    for i in range(40):
        time.sleep(2)
        st = json.loads(state())
        if st["dur"] and not st["paused"]:
            break
    print("  起播:", st)
    first = st["src"]

    print("\n--- 只听到约 6 秒就点「下一首」（预期记 skip）")
    time.sleep(6)
    ev("document.getElementById('rm-ai-next').click(); 'ok'")
    for i in range(20):
        time.sleep(2)
        st2 = json.loads(state())
        if st2["src"] != first and st2["dur"]:
            break
    print("  切到:", st2)

    print("\n--- 让它放满 35 秒（预期记 play）")
    time.sleep(38)
    print("  当前:", state())
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
