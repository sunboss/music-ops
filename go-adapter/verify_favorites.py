#!/usr/bin/env python3
"""验收「我喜欢」：真实浏览器点红心 -> 落本地 + 上报服务端 -> 音乐库可见 -> 按收藏生成电台"""
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
PORT = 9465
SITE = "https://music.1234r.com"
OUT = "/Users/sunboss/Desktop/AI/music-ops/docs/shots"
prof = tempfile.mkdtemp(prefix="rm-fav-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required",
                         "--window-size=1440,980", "about:blank"],
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
ws = websocket.create_connection(ws_url, timeout=180, max_size=64 * 1024 * 1024)
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


def click(sel):
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;e.scrollIntoView({block:'center'});"
           "var r=e.getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % sel)
    if not b or b == "null":
        return "无此元素 " + sel
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mouseMoved", x=c["x"], y=c["y"], button="none")
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    return "已点 " + sel


def shot(name):
    d = cmd("Page.captureScreenshot", format="jpeg", quality=88)
    open(os.path.join(OUT, name), "wb").write(base64.b64decode(d["data"]))
    return os.path.join(OUT, name)


try:
    cmd("Page.enable")
    cmd("Page.navigate", url=SITE + "/playlist/24381616")
    for _ in range(30):
        time.sleep(2)
        if (ev("document.querySelectorAll('.row').length") or 0) > 0:
            break
    ev("document.querySelector('.row').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))")
    time.sleep(6)
    cur = ev("""(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
        .$pinia._s.get('player');return s.queue[s.index]?.name||null;})()""")
    print("正在播:", cur)

    print("\n=== ① 打开全屏播放器，点红心")
    print(" ", click(".bar .pc"))
    time.sleep(2)
    print("  全屏播放器已开:", ev("!!document.querySelector('.fp')"))
    print(" ", click('.fp header .ib[title^="喜欢"]'))      # 按 title 选红心，别用 nth-child
    time.sleep(2)
    print("  本地收藏:", ev("JSON.parse(localStorage.getItem('rm-favorites')||'[]').map(x=>x.name).join(' / ')") or "(空)")
    print("  红心状态(on):", ev("!!document.querySelector('.fp header .ib.on')"))
    print("  截图:", shot("fav-1-liked.jpg"))

    print("\n=== ② 服务端是否收到（这是 AI 要用的那份）")
    time.sleep(2)
    for _ in range(10):
        # 带浏览器 UA：Cloudflare 会拦 urllib 默认 UA
        req = urllib.request.Request(SITE + "/api/favorites", headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")})
        srv = urllib.request.urlopen(req, timeout=15).read().decode()
        j = json.loads(srv)
        if j.get("count"):
            break
        time.sleep(2)
    print("  /api/favorites ->", json.dumps(j, ensure_ascii=False)[:160])

    print("\n=== ③ 音乐库 → 我喜欢的")
    cmd("Page.navigate", url=SITE + "/library")
    time.sleep(6)
    print(" ", click(".tabs button:nth-child(2)"))
    time.sleep(2)
    print("  Tab 标题:", ev("Array.from(document.querySelectorAll('.tabs button')).map(b=>b.textContent.trim()).join(' / ')"))
    print("  列表条目:", ev("Array.from(document.querySelectorAll('.row .nm')).map(e=>e.textContent).join(' / ')")[:120])
    print("  截图:", shot("fav-2-library.jpg"))

    print("\n=== ④ 按收藏生成电台（AI 拿到'明确收藏'上下文）")
    print(" ", click(".ops .ghost"))
    for _ in range(40):
        time.sleep(2)
        st = json.loads(ev("""JSON.stringify((function(){var s=document.getElementById('app').__vue_app__
            .config.globalProperties.$pinia._s.get('player');
            return {n:s.queue.length, cur:s.queue[s.index]?.name||null};})())"""))
        if st["n"] > 1 and st["cur"]:
            break
    print("  电台队列:", st["n"], "首 | 正在播:", st["cur"])
    print("  截图:", shot("fav-3-radio.jpg"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
