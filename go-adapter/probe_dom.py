#!/usr/bin/env python3
"""检查搜索结果页真实 DOM 结构，找出可点击的歌曲行"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9413


def start():
    prof = tempfile.mkdtemp(prefix="rm-dom-")
    proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                             "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
                             "--autoplay-policy=no-user-gesture-required", "--mute-audio",
                             "--remote-allow-origins=*", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
                if t.get("type") == "page":
                    return proc, prof, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("no chrome")


proc, prof, _ws_url = start()
ws = websocket.create_connection(_ws_url, timeout=30, max_size=32 * 1024 * 1024)


class C:
    i = 0

    @staticmethod
    def send(method, **p):
        C.i += 1
        ws.send(json.dumps({"id": C.i, "method": method, "params": p}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == C.i:
                return m.get("result", {})

    @staticmethod
    def ev(e):
        r = C.send("Runtime.evaluate", expression=e, returnByValue=True)
        return r.get("result", {}).get("value")


try:
    C.send("Page.enable")
    C.send("Page.navigate", url="https://music.1234r.com")
    time.sleep(7)
    C.ev("location.hash='#/search/'+encodeURIComponent('晴天')")
    time.sleep(7)
    print("== 页面里出现的类名统计（前 25）")
    print(C.ev("""JSON.stringify(Object.entries(
      [...document.querySelectorAll('*')].reduce((a,e)=>{for(const c of e.classList)a[c]=(a[c]||0)+1;return a;},{}))
      .sort((x,y)=>y[1]-x[1]).slice(0,25))"""))
    print()
    print("== 可能的列表容器结构")
    print(C.ev("""(() => {
      const cands = [...document.querySelectorAll('div')].filter(d => d.children.length>=5 && d.className);
      return JSON.stringify(cands.slice(0,6).map(d=>({cls:d.className, kids:d.children.length,
        firstKid:d.children[0] ? d.children[0].className : '', txt:(d.innerText||'').slice(0,60).replace(/\\n/g,'/')})), null, 1);
    })()"""))
    print()
    print("== 含歌名文本的最深可点击元素")
    print(C.ev("""(() => {
      const hits = [...document.querySelectorAll('a,div,li')].filter(e =>
        (e.innerText||'').includes('晴天') && e.querySelectorAll('*').length >= 1 && e.querySelectorAll('*').length <= 12);
      return JSON.stringify(hits.slice(0,6).map(e=>({tag:e.tagName, cls:e.className, href:e.getAttribute('href')||'',
        kids:e.querySelectorAll('*').length, txt:(e.innerText||'').slice(0,70).replace(/\\n/g,'/')})), null, 1);
    })()"""))
finally:
    ws.close()
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
