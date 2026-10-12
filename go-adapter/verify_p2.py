#!/usr/bin/env python3
"""P2 验收：发现 / 音乐库(含播放历史) / 设置 —— 全部用真实鼠标事件"""
import base64, json, os, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9450
BASE = "http://127.0.0.1:5199"
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
prof = tempfile.mkdtemp(prefix="rm-p2-")
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
ws = websocket.create_connection(ws_url, timeout=120, max_size=64*1024*1024)
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
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;var r=e.getBoundingClientRect();"
           "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % sel)
    if not b or b == "null": return "无此元素 " + sel
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mouseMoved", x=c["x"], y=c["y"], button="none")
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    return "已点击 " + sel
def shot(name):
    d = cmd("Page.captureScreenshot", format="png")
    open(os.path.join(OUT, name), "wb").write(base64.b64decode(d["data"]))
def wait(expr, secs=40):
    for _ in range(secs):
        if ev(expr): return True
        time.sleep(1)
    return False
try:
    cmd("Page.enable")
    # 1) 先播一首，产生历史
    cmd("Page.navigate", url=BASE + "/playlist/24381616")
    wait("document.querySelectorAll('.row').length>5")
    b = json.loads(ev("(function(){var e=document.querySelectorAll('.row')[0];var r=e.getBoundingClientRect();"
                      "return JSON.stringify({x:r.left+120,y:r.top+r.height/2});})()"))
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=b["x"], y=b["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=b["x"], y=b["y"], button="left", clickCount=ct)
        time.sleep(0.05)
    print("起播:", wait("!!document.querySelector('.bar .pc img')", 45))

    # 2) 音乐库：应看到刚才的历史
    cmd("Page.navigate", url=BASE + "/library")
    time.sleep(4)
    print("音乐库 最近播放条数:", ev("document.querySelectorAll('.page .row').length"),
          "| 标题:", ev("document.querySelector('h1')?.textContent"))
    shot("p2-library-1440.png")

    # 3) 发现
    cmd("Page.navigate", url=BASE + "/explore")
    wait("document.querySelectorAll('.card').length>6", 30)
    print("发现 卡片数:", ev("document.querySelectorAll('.card').length"),
          "| 分类按钮:", ev("document.querySelectorAll('.cats button').length"))
    click(".cats button:nth-child(4)")     # 切分类
    time.sleep(5)
    print("  切到第 4 个分类后卡片数:", ev("document.querySelectorAll('.card').length"))
    shot("p2-explore-1440.png")

    # 4) 设置：切深色
    cmd("Page.navigate", url=BASE + "/settings")
    time.sleep(3)
    print("设置 主题选项:", ev("document.querySelectorAll('.themes button').length"),
          "| 构建:", ev("document.querySelectorAll('.kv b')[0]?.textContent"))
    click(".themes button:nth-child(2)")   # 深色
    time.sleep(2)
    print("  点深色后 html.dark:", ev("document.documentElement.classList.contains('dark')"),
          "| 已保存提示:", ev("!!document.querySelector('.ok')"))
    shot("p2-settings-dark-1440.png")
    # 手机版设置
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    time.sleep(2)
    print("设置@390 溢出:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"))
    shot("p2-settings-390.png")
    cmd("Page.navigate", url=BASE + "/library")
    time.sleep(4)
    print("音乐库@390 溢出:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"),
          "| 历史条数:", ev("document.querySelectorAll('.page .row').length"))
    shot("p2-library-390.png")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
