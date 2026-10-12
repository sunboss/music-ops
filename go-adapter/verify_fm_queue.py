#!/usr/bin/env python3
"""验收：私人 FM + 播放队列抽屉（局域网地址 + 真实鼠标事件 + 真实播放判定）"""
import base64, json, os, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9453
LAN = "http://192.168.1.174:5199"
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
prof = tempfile.mkdtemp(prefix="rm-fmq-")
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
    return "已点 " + sel
def shot(name):
    d = cmd("Page.captureScreenshot", format="png")
    open(os.path.join(OUT, name), "wb").write(base64.b64decode(d["data"]))
ST = """(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia.state.value.player;return JSON.stringify({cur:s.queue[s.index]?s.queue[s.index].name:null,
    n:s.queue.length, i:s.index, playing:s.playing, prog:+s.progress.toFixed(1),
    showQueue:s.showQueue, err:s.error});})()"""
try:
    cmd("Page.enable")
    # 1) 从歌单起播（保证有队列）
    cmd("Page.navigate", url=LAN + "/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"): break
        time.sleep(1)
    b = json.loads(ev("(function(){var e=document.querySelectorAll('.row')[0];var r=e.getBoundingClientRect();"
                      "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()"))
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=b["x"], y=b["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=b["x"], y=b["y"], button="left", clickCount=ct)
        time.sleep(0.05)
    for _ in range(30):
        time.sleep(2)
        if json.loads(ev(ST))["prog"] > 2: break
    print("起播:", ev(ST))

    # 2) 打开队列抽屉
    print(click(".bar .pc"))
    time.sleep(2)
    print(click(".fp .ctl2 .ib.sm"))
    time.sleep(1.5)
    st = json.loads(ev(ST))
    print("队列抽屉打开:", st["showQueue"], "| 抽屉内条目:",
          ev("document.querySelectorAll('.qd .item').length"),
          "| 接下来:", ev("document.querySelectorAll('.qd .list .item').length"))
    shot("queue-desktop.png")
    # 点队列里第 3 首跳转
    print(ev("""(function(){var it=document.querySelectorAll('.qd .list .item')[2];
        return it? it.innerText.replace(/\n/g,' / ').slice(0,40):'无';})()"""))
    click(".qd .list .item:nth-child(3)")
    time.sleep(3)
    print("跳转后:", ev(ST))
    print(click(".qd header .ib"))

    # 3) 私人 FM
    cmd("Page.navigate", url=LAN + "/fm")
    time.sleep(6)
    print("\nFM 页标题:", ev("document.querySelector('h1')?.textContent"))
    for _ in range(30):
        time.sleep(2)
        if ev("!!document.querySelector('.card .big')"): break
    print("FM 卡片:", ev("!!document.querySelector('.card')"),
          "| 曲名:", ev("document.querySelector('.card .nm')?.textContent"),
          "| 状态:", ev("document.querySelector('.stat')?.textContent"))
    shot("fm-desktop.png")
    # 不感兴趣 -> 切歌
    before = ev("document.querySelector('.card .nm')?.textContent")
    click(".card .ib.no")
    time.sleep(6)
    after = ev("document.querySelector('.card .nm')?.textContent")
    print("点「不感兴趣」: %r -> %r  %s" % (before, after, "✓ 已切歌" if before != after else "✗ 未切换"))
    # 移动端看队列抽屉
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    time.sleep(2)
    print("FM@390 溢出:", ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth"))
    shot("fm-mobile.png")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
