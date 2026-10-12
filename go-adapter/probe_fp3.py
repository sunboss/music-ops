#!/usr/bin/env python3
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9446
prof = tempfile.mkdtemp(prefix="rm-fp3-")
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
ST = """(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia.state.value.player; return JSON.stringify({cur:s.queue[s.index]?s.queue[s.index].name:null,
    playing:s.playing, showFull:s.showFull, dur:s.duration, prog:Math.round(s.progress), err:s.error});})()"""
try:
    cmd("Page.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"): break
        time.sleep(1)
    ev("document.querySelectorAll('.row')[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2})); 'ok'")
    print("等待起播…")
    for i in range(40):
        time.sleep(2)
        st = ev(ST)
        if '"cur":' in st and '"cur":null' not in st:
            print("  起播状态:", st); break
    else:
        print("  超时未起播:", ev(ST))
    print("点播放条封面…")
    ev("document.querySelector('.pc').click(); 'ok'")
    time.sleep(2)
    print("  状态:", ev(ST))
    print("  .fp 已渲染:", ev("!!document.querySelector('.fp')"))
    print("  歌词行数:", ev("document.querySelectorAll('.fp .ln').length"))
    print("  当前曲名:", ev("document.querySelector('.fp .nm')?.textContent"))
    print("  高亮行:", ev("document.querySelector('.fp .ln.on')?.textContent?.slice(0,28)"))
    import base64
    d = cmd("Page.captureScreenshot", format="png")
    open('/Users/sunboss/Desktop/AI/music-ops/analysis/fullplayer-desktop.png','wb').write(base64.b64decode(d["data"]))
    print("  已截图 fullplayer-desktop.png")
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    time.sleep(2)
    d = cmd("Page.captureScreenshot", format="png")
    open('/Users/sunboss/Desktop/AI/music-ops/analysis/fullplayer-mobile.png','wb').write(base64.b64decode(d["data"]))
    print("  已截图 fullplayer-mobile.png")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
