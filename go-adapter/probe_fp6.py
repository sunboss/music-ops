#!/usr/bin/env python3
"""用 CDP 真实鼠标事件点击播放条封面（等同真人操作）"""
import base64, json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9449
prof = tempfile.mkdtemp(prefix="rm-fp6-")
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
ws = websocket.create_connection(ws_url, timeout=90, max_size=32*1024*1024)
n = [0]
def cmd(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]: return r.get("result", {})
def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:200]
    return r.get("result", {}).get("value")
def real_click(sel):
    box = ev("(function(){var e=document.querySelector(%r);if(!e)return null;var r=e.getBoundingClientRect();"
             "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % sel)
    if not box or box == "null": return "元素不存在: " + sel
    p = json.loads(box)
    cmd("Input.dispatchMouseEvent", type="mouseMoved", x=p["x"], y=p["y"], button="none")
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"], y=p["y"], button="left", clickCount=1)
    return "已点击 (%d,%d)" % (p["x"], p["y"])
ST = """(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia.state.value.player;return JSON.stringify({cur:s.queue[s.index]?s.queue[s.index].name:null,
    full:s.showFull, playing:s.playing});})()"""
try:
    cmd("Page.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"): break
        time.sleep(1)
    # 用真实双击播放第一首
    b = json.loads(ev("(function(){var e=document.querySelectorAll('.row')[0];var r=e.getBoundingClientRect();"
                      "return JSON.stringify({x:r.left+120,y:r.top+r.height/2});})()"))
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=b["x"], y=b["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=b["x"], y=b["y"], button="left", clickCount=ct)
        time.sleep(0.05)
    for i in range(40):
        time.sleep(2)
        if ev("!!document.querySelector('.bar .pc img')"): break
    print("起播状态:", ev(ST))
    print(real_click(".bar .pc"))
    time.sleep(2)
    print("点击后:", ev(ST))
    print(".fp 渲染:", ev("!!document.querySelector('.fp')"), "| 歌词行数:",
          ev("document.querySelectorAll('.fp .ln').length"))
    print("当前曲名:", ev("document.querySelector('.fp .nm')?.textContent"))
    if ev("!!document.querySelector('.fp')"):
        d = cmd("Page.captureScreenshot", format="png")
        open('/Users/sunboss/Desktop/AI/music-ops/analysis/fullplayer-desktop.png','wb').write(base64.b64decode(d["data"]))
        cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        time.sleep(2)
        d = cmd("Page.captureScreenshot", format="png")
        open('/Users/sunboss/Desktop/AI/music-ops/analysis/fullplayer-mobile.png','wb').write(base64.b64decode(d["data"]))
        print("已截图 桌面/手机两版")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
