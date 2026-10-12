#!/usr/bin/env python3
"""P1 页面验收：专辑/歌手/搜索/每日推荐 —— 三档宽度渲染与溢出检查"""
import base64, json, os, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9442
BASE = "http://127.0.0.1:5199"
OUT = "/Users/sunboss/Desktop/AI/music-ops/analysis"
prof = tempfile.mkdtemp(prefix="rm-p1-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + prof, "--no-first-run", "--remote-allow-origins=*", "--mute-audio",
    "--window-size=1440,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:140]
    return r.get("result", {}).get("value")
def shot(name):
    d = cmd("Page.captureScreenshot", format="png")
    open(os.path.join(OUT, name), "wb").write(base64.b64decode(d["data"]))

CASES = [("专辑", "/album/32311", "document.querySelector('h1')?.textContent"),
         ("歌手", "/artist/6452", "document.querySelectorAll('.row').length>3"),
         ("搜索", "/search/%E5%91%A8%E6%9D%B0%E4%BC%A6", "document.querySelectorAll('.row').length>3"),
         ("每日推荐", "/daily/songs", "1")]
for w, h, tag in [(1440, 900, "1440"), (390, 844, "390")]:
    cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if w < 700 else 1, mobile=w < 700)
    for label, path, hold in CASES:
        cmd("Page.navigate", url=BASE + path)
        time.sleep(4)
        for _ in range(24):
            if ev(hold): break
            time.sleep(2)
        time.sleep(1.2)
        over = ev("document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth")
        rows = ev("document.querySelectorAll('.row').length")
        h1 = ev("document.querySelector('h1')?.textContent")
        print("  %-8s %-5s h1=%-22r 行=%-5s 溢出=%s" % (label, tag, (h1 or "")[:20], rows, over))
        shot("p1-%s-%s.png" % (label, tag))
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
try: ws.close()
except Exception: pass
proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
