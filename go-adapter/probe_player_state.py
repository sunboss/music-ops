#!/usr/bin/env python3
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9444
prof = tempfile.mkdtemp(prefix="rm-ps-")
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
n = [0]; logs = []
def cmd(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("method") == "Runtime.consoleAPICalled":
            logs.append(" ".join(str(a.get("value",""))[:80] for a in r["params"].get("args",[])))
        if r.get("method") == "Runtime.exceptionThrown":
            logs.append("EXC " + str(r["params"]["exceptionDetails"].get("exception",{}).get("description"))[:160])
        if r.get("id") == n[0]: return r.get("result", {})
def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:200]
    return r.get("result", {}).get("value")
STATE = """(function(){
  var app = document.getElementById('app').__vue_app__;
  var pin = app && app.config.globalProperties.$pinia;
  var s = pin && pin.state.value && pin.state.value.player;
  if (!s) return 'no player state';
  return JSON.stringify({queue: s.queue.length, index: s.index, playing: s.playing, loading: s.loading,
    progress: s.progress, duration: s.duration, error: s.error, showFull: s.showFull,
    cur: s.queue[s.index] ? s.queue[s.index].name : null});
})()"""
try:
    cmd("Page.enable"); cmd("Runtime.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"): break
        time.sleep(1)
    print("行数:", ev("document.querySelectorAll('.row').length"))
    print("点击前状态:", ev(STATE))
    ev("document.querySelectorAll('.row')[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2})); 'ok'")
    time.sleep(6)
    print("点击后状态:", ev(STATE))
    print("迷你条/播放条:", ev("!!document.querySelector('.mini')"), ev("!!document.querySelector('.pc')"))
    print("controls 上的 .row 是否 dead:", ev("document.querySelectorAll('.row')[0].className"))
    print("\n=== 页面日志")
    for l in logs[-10:]: print("   ", l)
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
