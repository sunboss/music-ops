#!/usr/bin/env python3
"""诊断：搜索结果页第一行到底怎么点才会播放"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9415
SITE = "https://music.1234r.com"


class C:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=30, max_size=64 * 1024 * 1024)
        self.i = 0

    def send(self, method, **p):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": p}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                return m.get("result", {})

    def ev(self, e):
        r = self.send("Runtime.evaluate", expression=e, returnByValue=True)
        return r.get("result", {}).get("value")

    def click(self, x, y, count=1):
        for _ in range(count):
            self.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
            self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)


prof = tempfile.mkdtemp(prefix="rm-diag-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--autoplay-policy=no-user-gesture-required",
                         "--mute-audio", "--window-size=1440,900", "--remote-allow-origins=*", "about:blank"],
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

c = C(ws_url)
try:
    c.send("Page.enable")
    c.send("Runtime.enable")
    c.send("Log.enable")
    c.send("Page.navigate", url=SITE + "/search/" + urllib.parse.quote("晴天"))
    time.sleep(9)
    c.ev("""(() => { window.__probe=[];
      const op=HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play=function(){ if(!window.__probe.includes(this)) window.__probe.push(this); return op.apply(this,arguments); };
      window.__errs=[]; window.addEventListener('error',e=>window.__errs.push(String(e.message)));
      return true; })()""")

    print("行数:", c.ev("document.querySelectorAll('.track').length"))
    print("第一行结构:")
    print(c.ev("""(() => { const r=document.querySelector('.track');
      return JSON.stringify({cls:r.className, html:r.outerHTML.slice(0,420)}); })()"""))
    print()
    print("行内子元素坐标:")
    print(c.ev("""(() => { const r=document.querySelector('.track');
      return JSON.stringify([...r.querySelectorAll('*')].slice(0,10).map(e=>{const b=e.getBoundingClientRect();
        return {tag:e.tagName, cls:e.className, x:Math.round(b.x), y:Math.round(b.y), w:Math.round(b.width), h:Math.round(b.height)};}),null,1); })()"""))

    box = c.ev("""(() => { const t=document.querySelector('.track .title')||document.querySelector('.track');
      const b=t.getBoundingClientRect(); return {x:Math.round(b.x+b.width/2), y:Math.round(b.y+b.height/2)}; })()""")
    print()
    print("点击 .title 中心:", box)
    c.click(box["x"], box["y"])
    time.sleep(4)
    print("  勾子捕获的音频数:", c.ev("(window.__probe||[]).length"))
    print("  页面 audio 元素:", c.ev("document.querySelectorAll('audio').length"))
    print("  播放条文本:", c.ev("(document.querySelector('.player')||{}).innerText"))
    print("  页面错误:", c.ev("JSON.stringify(window.__errs||[])"))

    print()
    print("改用 JS 直接 click 行元素 ...")
    c.ev("document.querySelector('.track').click()")
    time.sleep(4)
    print("  勾子捕获的音频数:", c.ev("(window.__probe||[]).length"))
    print("  播放条文本:", c.ev("(document.querySelector('.player')||{}).innerText"))
    print("  音频状态:", c.ev("""(() => { const a=(window.__probe||[])[0]||document.querySelector('audio');
      return a ? JSON.stringify({src:a.src.slice(-60), paused:a.paused, t:a.currentTime, d:a.duration, ready:a.readyState}) : '无音频对象'; })()"""))
finally:
    try:
        c.ws.close()
    except Exception:
        pass
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
