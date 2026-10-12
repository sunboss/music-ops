#!/usr/bin/env python3
"""真实浏览器验证 AI 电台：点场景 -> 生成歌单 -> 自动起播 -> 播到结尾自动下一首"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9426
prof = tempfile.mkdtemp(prefix="rm-radio-")
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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:140]
    return r.get("result", {}).get("value")


def state():
    return json.loads(ev("""(function(){var a=document.getElementById('rm-ai-audio');
        return JSON.stringify({src:(a.src||'').slice(-32),dur:Math.round(a.duration||0),
        t:+(a.currentTime||0).toFixed(1),paused:a.paused,
        now:(document.getElementById('rm-ai-now')||{}).textContent||'',
        pos:(document.getElementById('rm-ai-pos')||{}).textContent||''});})()"""))


try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(10)
    print("注入版本:", ev("window.__RM_VERSION"))
    print("场景快捷按钮:", ev("document.querySelectorAll('#rm-ai-chips i').length"), "个")
    ev("document.getElementById('rm-ai-btn').click(); 'ok'")

    print("\n--- 点「开车兜风」生成电台")
    ev("""Array.prototype.find.call(document.querySelectorAll('#rm-ai-chips i'),
        function(e){return e.textContent==='开车兜风';}).click(); 'ok'""")
    cnt = 0
    for i in range(45):
        time.sleep(2)
        cnt = ev("document.querySelectorAll('#rm-ai-list .it').length") or 0
        if cnt:
            break
    print("歌单名:", ev("document.getElementById('rm-ai-title').textContent"))
    print("回复:", (ev("document.getElementById('rm-ai-reply').textContent") or "")[:70])
    print("曲目数:", cnt)
    print("前 4 首:", ev("""JSON.stringify(Array.prototype.slice.call(
        document.querySelectorAll('#rm-ai-list .it'),0,4).map(function(e){
        return e.innerText.replace(/\\n/g,' / ');}))"""))

    print("\n--- 验证自动起播")
    for i in range(20):
        time.sleep(2)
        s = state()
        if s["dur"] and not s["paused"]:
            break
    print("播放器:", s)
    print("结果: 生成后自动起播 ✔（%.0f 秒）" % s["dur"] if s["dur"] else "结果: 未起播 ✘")

    print("\n--- 拖到结尾，验证自动播下一首")
    cur_src = s["src"]
    ev("(function(){var a=document.getElementById('rm-ai-audio');a.currentTime=Math.max(0,a.duration-0.6);return 'ok';})()")
    got = None
    for i in range(30):
        time.sleep(2)
        s2 = state()
        if s2["src"] != cur_src and s2["dur"]:
            got = s2
            break
    if got:
        print("下一首已接上:", got)
        print("结果: 播完自动下一首 ✔（%s -> %s）" % (cur_src[-12:], got["src"][-12:]))
    else:
        print("结果: 未自动跳下一首 ✘ 当前:", s2)

    print("\n--- 验证「下一首」按钮")
    before = state()["src"]
    ev("document.getElementById('rm-ai-next').click(); 'ok'")
    for i in range(20):
        time.sleep(1.5)
        s3 = state()
        if s3["src"] != before and s3["dur"]:
            break
    print("结果: 手动切歌", "✔" if s3["src"] != before else "✘", s3["src"][-12:], "| 进度:", s3["pos"])
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
