#!/usr/bin/env python3
"""移动端歌单页空白排查：直接开新页打开，不靠 SPA 内跳"""
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9433
prof = tempfile.mkdtemp(prefix="rm-mob-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + prof, "--no-first-run", "--mute-audio", "--remote-allow-origins=*",
    "--window-size=390,844", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:150]
    return r.get("result", {}).get("value")
try:
    cmd("Page.enable")
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    cmd("Page.navigate", url="https://music.1234r.com/playlist/24381616")
    time.sleep(16)
    print("body 文字长度:", len(ev("document.body.innerText") or ""))
    print("body 前 260 字:", (ev("document.body.innerText") or "")[:260].replace("\n", " | "))
    print("控制台报错:", ev("window.__rmErrs || '无'"))
    print("\n=== 列表容器")
    print(ev("""JSON.stringify(['.playlist','.track-list','[class*=track]','[class*=list]','table']
        .map(function(s){ try { return s+'='+document.querySelectorAll(s).length } catch(e){ return s+'=err' } }))"""))
    print("\n=== 可见元素数量（排除导航）")
    print(ev("""(function(){var c=document.getElementById('app'); if(!c) return 'no app';
        return 'app 子节点='+c.querySelectorAll('*').length;})()"""))
    import base64
    d = cmd("Page.captureScreenshot", format="png")
    open('/Users/sunboss/Desktop/AI/music-ops/analysis/playlist-390-fresh.png','wb').write(base64.b64decode(d["data"]))
    print("已截图: playlist-390-fresh.png")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
