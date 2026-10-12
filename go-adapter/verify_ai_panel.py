#!/usr/bin/env python3
"""真实浏览器验证 AI 点歌浮窗：打开面板 -> 输入需求 -> 看回复与歌曲列表 -> 点歌播放"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9425

prof = tempfile.mkdtemp(prefix="rm-ai-")
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

ws = websocket.create_connection(ws_url, timeout=90, max_size=64 * 1024 * 1024)
n = [0]


def cmd(m, **p):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]:
            return r.get("result", {})


def ev(e, awaitp=True):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=awaitp)
    if "exceptionDetails" in r:
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:150]
    return r.get("result", {}).get("value")


try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(10)
    print("注入版本:", ev("window.__RM_VERSION"))
    print("AI 按钮存在:", ev("!!document.getElementById('rm-ai-btn')"))
    print("面板存在:", ev("!!document.getElementById('rm-ai-panel')"))

    print("\n--- 打开面板并输入「放点能完整播放的周杰伦经典」")
    print("点击按钮:", ev("document.getElementById('rm-ai-btn').click(); document.getElementById('rm-ai-panel').style.display"))
    ev("document.getElementById('rm-ai-input').value = '放点能完整播放的周杰伦经典'")
    ev("document.getElementById('rm-ai-go').click(); 'clicked'")
    for i in range(15):
        time.sleep(2)
        rep = ev("document.getElementById('rm-ai-reply').textContent")
        cnt = ev("document.querySelectorAll('#rm-ai-list .it').length")
        if rep and rep != "想一下…" and cnt:
            break
    print("AI 回复:", rep)
    print("返回歌曲数:", cnt)
    print("前 3 首:", ev("""JSON.stringify(Array.prototype.slice.call(
        document.querySelectorAll('#rm-ai-list .it')).slice(0,3).map(function(e){
        return e.innerText.replace(/\\n/g,' / ');}))"""))

    print("\n--- 点击第一首歌，验证能播放")
    ev("document.querySelectorAll('#rm-ai-list .it')[0].click(); 'ok'")
    for i in range(12):
        time.sleep(2)
        st = ev("""(function(){var a=document.getElementById('rm-ai-audio');
            return JSON.stringify({src:(a.src||'').slice(-40),dur:a.duration||0,t:a.currentTime||0,
                                   paused:a.paused, ready:a.readyState});})()""")
        d = json.loads(st)
        if d.get("dur"):
            break
    print("播放器状态:", st)
    if d.get("dur", 0) > 120:
        print("结论: 面板内点歌并完整加载音频 ✔（%.0f 秒）" % d["dur"])
    elif d.get("src"):
        print("结论: 已加载音频，时长", d.get("dur"))
    else:
        print("结论: 未取到音频 ✘")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
