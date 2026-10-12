#!/usr/bin/env python3
"""现状分析：路由表、关键页面结构、三档宽度截图"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9431
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
os.makedirs(OUT, exist_ok=True)

prof = tempfile.mkdtemp(prefix="rm-ana-")
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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:150]
    return r.get("result", {}).get("value")


def shot(name, w, h):
    cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if w < 500 else 1,
        mobile=w < 500)
    time.sleep(2.5)
    d = cmd("Page.captureScreenshot", format="png", captureBeyondViewport=False)
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(__import__("base64").b64decode(d["data"]))
    print("   截图:", path)
    return path


try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(13)

    print("=== 运行时路由表")
    print(ev("""(function(){
      var el = document.getElementById('app');
      var vm = el && (el.__vue__ || (el.children[0] && el.children[0].__vue__));
      var r = vm && vm.$router;
      if (!r) return '拿不到 router';
      return JSON.stringify(r.options.routes.map(function(x){
        return {path: x.path, name: x.name || '', comp: (x.component && (x.component.name||'anon')) || 'child'};
      }), null, 0);
    })()""")[:1500])

    print("\n=== 主题与骨架")
    print("  注入脚本:", ev("!!window.__RM_VERSION && window.__RM_VERSION"))
    print("  body class:", ev("document.body.className"))
    print("  顶层结构:", ev("""(function(){
      var c=document.getElementById('app'); if(!c) return 'no #app';
      return Array.from(c.children).map(function(e){return e.tagName+'.'+(e.className||'').toString().slice(0,40);}).join(' > ');
    })()"""))
    print("  样式表数量:", ev("document.styleSheets.length"))
    print("  含媒体查询的规则数:", ev("""(function(){
      var n=0;
      for (var i=0;i<document.styleSheets.length;i++){
        var ss=document.styleSheets[i], rules;
        try { rules = ss.cssRules; } catch(e){ continue; }
        if (!rules) continue;
        for (var j=0;j<rules.length;j++){
          if (rules[j].type === CSSRule.MEDIA_RULE) n++;
        }
      }
      return n;
    })()"""))

    print("\n=== 首页三档宽度截图")
    shot("home-1440.png", 1440, 900)
    shot("home-768.png", 768, 1024)
    shot("home-390.png", 390, 844)

    print("\n=== 移动端是否溢出（横向滚动）")
    print("  scrollWidth/clientWidth:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"))

    print("\n=== 主要页面集合")
    cmd("Emulation.clearDeviceMetricsOverride")
    cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
    for label, path in [("search", "/search/%E5%91%A8%E6%9D%B0%E4%BC%A6"),
                        ("daily", "/daily"), ("library", "/library"),
                        ("playlist", "/playlist/24381616"),
                        ("artist", "/artist/6452")]:
        ev("location.href='https://music.1234r.com%s'; 'go'" % path)
        time.sleep(7)
        body = (ev("document.body.innerText") or "")[:90].replace("\n", " | ")
        print("  %-9s %-28s -> %s" % (label, path, body))
        shot("page-%s.png" % label, 1440, 900)
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
print("\n分析产物目录:", OUT)
