#!/usr/bin/env python3
"""调试：为什么页面里的 JS 求值返回空"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9416

prof = tempfile.mkdtemp(prefix="rm-dbg-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run",
                         "--autoplay-policy=no-user-gesture-required", "--mute-audio",
                         "--window-size=1440,900", "--remote-allow-origins=*", "about:blank"],
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

ws = websocket.create_connection(ws_url, timeout=30, max_size=64 * 1024 * 1024)
n = [0]


def raw(expr):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == n[0]:
            return m


try:
    raw("1")
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": "Page.enable"}))
    ws.recv()
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": "Page.navigate",
                        "url": "https://music.1234r.com/search/" + urllib.parse.quote("晴天")}))
    time.sleep(9)

    print("行数:", raw("document.querySelectorAll('.track').length").get("result", {}).get("value"))

    tests = {
        "取第一行": "document.querySelectorAll('.track')[0] ? 'yes' : 'no'",
        "取innerText": "(document.querySelectorAll('.track')[0].innerText||'').slice(0,20)",
        "正则替换": "(document.querySelectorAll('.track')[0].innerText||'').replace(/[\\r\\n]+/g,' / ').slice(0,30)",
        "派发dblclick": """(() => { const r=document.querySelectorAll('.track')[0];
            r.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true,view:window,detail:2}));
            return 'dispatched'; })()""",
        "完整片段": """(() => {
            const r = document.querySelectorAll('.track')[0];
            if (!r) return 'NONE';
            const nm = (r.innerText || '').replace(/[\\r\\n]+/g, ' / ').slice(0, 40);
            ['mousedown','mouseup','click','dblclick'].forEach(function (k) {
              r.dispatchEvent(new MouseEvent(k, {bubbles: true, cancelable: true, view: window,
                detail: (k === 'dblclick') ? 2 : 1}));
            });
            return nm; })()""",
    }
    for name, expr in tests.items():
        res = raw(expr)
        if "exceptionDetails" in res.get("result", {}):
            print("  %-12s 抛错: %s" % (name, json.dumps(res["result"]["exceptionDetails"], ensure_ascii=False)[:220]))
        else:
            print("  %-12s -> %s" % (name, json.dumps(res.get("result", {}).get("result", {}).get("value"), ensure_ascii=False)[:120]))
    time.sleep(5)
    print("播放条:", raw("(document.querySelector('.player')||{}).innerText"))
    print("音频:", raw("""(() => { const c=(window.__probe||[]).concat([...document.querySelectorAll('audio')]);
        const a=c.find(x=>x&&x.duration>0)||c[0]; return a? JSON.stringify({src:a.src.slice(-50),t:a.currentTime,d:a.duration,paused:a.paused}) : '无'; })()""").get("result", {}).get("result", {}).get("value"))
finally:
    ws.close()
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
