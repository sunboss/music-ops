#!/usr/bin/env python3
"""验收投屏 UI 与「不再灰化」：生产域名真实浏览器"""
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
PORT = 9458
SITE = "https://music.1234r.com"
OUT = "/Users/sunboss/Desktop/AI/music-ops/docs/shots"
prof = tempfile.mkdtemp(prefix="rm-cast-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required",
                         "--window-size=1440,900", "about:blank"],
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


ST = """(function(){var st=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia._s.get('player');return JSON.stringify({cur:st.queue[st.index]?st.queue[st.index].name:null,
    n:st.queue.length, showCast:st.showCast, castName:st.castName, prog:+st.progress.toFixed(1)});})()"""

try:
    cmd("Page.enable")
    # 1) 歌单页：确认不再灰化
    cmd("Page.navigate", url=SITE + "/playlist/24381616")
    for _ in range(30):                      # 1000 行的歌单要等数据+渲染
        time.sleep(2)
        if (ev("document.querySelectorAll('.row').length") or 0) > 0:
            break
    print("① 不再灰化（全部可点）")
    print("   行数:", ev("document.querySelectorAll('.row').length"))
    print("   禁用的播放入口:", ev("document.querySelectorAll('.row .pv[disabled]').length"), "（应为 0）")
    print("   有 opacity<1 的灰行:", ev("Array.from(document.querySelectorAll('.row')).filter(r=>getComputedStyle(r).opacity<1).length"), "（应为 0）")
    print("   仍标注「取源失败」的行:", ev("Array.from(document.querySelectorAll('.row .du')).filter(d=>d.textContent.includes('取源失败')).length"))

    # 2) 起播一首，投屏按钮才有意义
    print("\n② 起播后看投屏入口")
    b = ev("(function(){var e=document.querySelector('.row:nth-child(1) .pv')||document.querySelector('.row');"
           "e.scrollIntoView({block:'center'});var r=e.getBoundingClientRect();"
           "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()")
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    time.sleep(2)
    for _ in range(30):
        time.sleep(2)
        if json.loads(ev(ST))["prog"] > 1:
            break
    print("   正在播:", json.loads(ev(ST))["cur"])
    print("   投屏按钮存在:", ev("!!document.querySelector('.bar .cast')"))

    print("\n③ 打开投屏面板（未配置 HA 时应给出明确入口，不假装能用）")
    print(" ", click(".bar .cast"))
    time.sleep(1.5)
    print("   面板已开:", json.loads(ev(ST))["showCast"])
    print("   文案:", (ev("document.querySelector('.sheet .empty p')?.textContent") or "")[:60])
    print("   有「去设置」按钮:", ev("!!document.querySelector('.sheet .empty .go')"))
    print("   截图:", shot("live-cast-empty.jpg"))

    print("\n④ 设置页的投屏配置项")
    print(" ", click(".sheet .empty .go"))
    time.sleep(3)
    print("   地址框:", ev("!!document.querySelector('.ha input[placeholder*=\"8123\"]')"),
          "| 令牌框:", ev("!!document.querySelector('.ha input[type=password]')"),
          "| 保存/测试:", ev("Array.from(document.querySelectorAll('.haops button')).map(b=>b.textContent.trim()).join('/')"))
    print("   截图:", shot("live-cast-settings.jpg"))

    # 5) 填一个假的 HA 地址，验证错误提示是否可照做（不假装成功）
    print("\n⑤ 填错误地址 → 提示要能照着做")
    ev("""(function(){var i=document.querySelector('.ha input[placeholder*="8123"]');
        i.value='http://192.168.1.240:8123';i.dispatchEvent(new Event('input',{bubbles:true}));
        var t=document.querySelector('.ha input[type=password]');
        t.value='fake-token-for-test';t.dispatchEvent(new Event('input',{bubbles:true}));return 'ok';})()""")
    click(".haops button:nth-child(2)")
    for _ in range(20):
        time.sleep(2)
        msg = ev("document.querySelector('.ha .bad, .ha .ok')?.textContent")
        if msg:
            break
    print("   提示:", (msg or "(无)")[:130])
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
