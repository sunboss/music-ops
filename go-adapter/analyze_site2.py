#!/usr/bin/env python3
"""补两张关键证据：移动端歌单页 + 桌面播放条"""
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
PORT = 9432
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
os.makedirs(OUT, exist_ok=True)
prof = tempfile.mkdtemp(prefix="rm-ana2-")
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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:130]
    return r.get("result", {}).get("value")


def shot(name):
    d = cmd("Page.captureScreenshot", format="png")
    with open(os.path.join(OUT, name), "wb") as f:
        f.write(base64.b64decode(d["data"]))
    print("   截图:", name)


try:
    cmd("Page.enable")
    # 1) 桌面：让 AI 面板放一首歌，看播放条
    cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(13)
    ev("document.getElementById('rm-ai-btn').click(); 'ok'")
    ev("""Array.prototype.find.call(document.querySelectorAll('#rm-ai-chips i'),
        function(e){return e.textContent==='深夜写代码';}).click(); 'ok'""")
    for i in range(30):
        time.sleep(2)
        if "正在播放" in (ev("document.getElementById('rm-ai-now').textContent") or ""):
            break
    print("  播放中:", ev("document.getElementById('rm-ai-now').textContent"))
    shot("player-desktop.png")

    print("\n=== 播放条 DOM 与尺寸")
    print("  ", ev("""(function(){
      var el=document.querySelector('.player')||document.querySelector('[class*=player]');
      if(!el) return '找不到 .player';
      var r=el.getBoundingClientRect();
      return JSON.stringify({cls:el.className, h:Math.round(r.height), y:Math.round(r.top),
        bg:getComputedStyle(el).backgroundColor, blur:getComputedStyle(el).backdropFilter});
    })()"""))

    # 2) 移动端歌单页
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    ev("location.href='https://music.1234r.com/playlist/24381616'; 'go'")
    time.sleep(9)
    shot("playlist-390.png")
    print("\n=== 移动端歌单页")
    print("  横向溢出:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"))
    print("  播放条是否可见:", ev("""(function(){var p=document.querySelector('.player');
        if(!p) return '无播放条元素';
        var r=p.getBoundingClientRect();
        return 'bottom='+Math.round(r.bottom)+' h='+Math.round(r.height)+' 视口='+window.innerHeight;})()"""))
    print("  底部导航:", ev("""(function(){
      var navs=[].slice.call(document.querySelectorAll('nav,footer,[class*=tabbar],[class*=mobile]'));
      return navs.length ? navs.map(function(e){return e.tagName+'.'+(e.className||'').slice(0,30)}).join(' | ') : '无';
    })()"""))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
