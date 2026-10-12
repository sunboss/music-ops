#!/usr/bin/env python3
"""验证：点投屏图标不再弹「页面」，只出现极小的设备菜单 / 一行提示（Chrome 隔离验证）"""
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9464; SITE = "https://music.1234r.com"
prof = tempfile.mkdtemp(prefix="rm-nopage-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + prof, "--no-first-run", "--mute-audio", "--remote-allow-origins=*",
    "--autoplay-policy=no-user-gesture-required", "--window-size=1440,900", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws_url = None
for _ in range(40):
    try:
        for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
            if t.get("type") == "page": ws_url = t["webSocketDebuggerUrl"]; break
        if ws_url: break
    except Exception: pass
    time.sleep(0.5)
ws = websocket.create_connection(ws_url, timeout=180, max_size=64*1024*1024)
n = [0]
def cmd(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]: return r.get("result", {})
def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:150]
    return r.get("result", {}).get("value")
def click(sel):
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;e.scrollIntoView({block:'center'});"
           "var r=e.getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % sel)
    if not b or b == "null": return "无此元素 " + sel
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mouseMoved", x=c["x"], y=c["y"], button="none")
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    return "已点 " + sel
try:
    cmd("Page.enable")
    cmd("Page.navigate", url=SITE + "/playlist/24381616")
    for _ in range(30):
        time.sleep(2)
        if (ev("document.querySelectorAll('.row').length") or 0) > 0: break
    ev("document.querySelector('.row').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))")
    time.sleep(6)
    print("正在播:", ev("""(function(){var st=document.getElementById('app').__vue_app__
        .config.globalProperties.$pinia._s.get('player');return st.queue[st.index]?.name||null;})()"""))
    print("投屏按钮存在:", ev("!!document.querySelector('.bar .cast')"))
    print("\n点击投屏图标 →")
    print(" ", click(".bar .cast"))
    time.sleep(4)
    big = ev("document.querySelectorAll('.mask .sheet').length")
    small = ev("!!document.querySelector('.wrap .menu')")
    toast = ev("document.querySelector('.toast')?.textContent || ''")
    print("  整页面板(.sheet):", big, "（应为 0）")
    print("  小菜单(.menu)  :", small)
    print("  一行提示(toast):", repr(toast))
    print("  菜单内容:", ev("Array.from(document.querySelectorAll('.menu .row span, .menu .hd, .menu .tip')).map(e=>e.textContent.trim()).join(' | ')")[:150])
    print("  菜单尺寸:", ev("(function(){var m=document.querySelector('.menu');if(!m)return '-';var r=m.getBoundingClientRect();"
        "return Math.round(r.width)+'x'+Math.round(r.height)+' @ 右下角';})()"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
