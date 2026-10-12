#!/usr/bin/env python3
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9445
prof = tempfile.mkdtemp(prefix="rm-fp2-")
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
n = [0]; errs = []
def cmd(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("method") == "Runtime.exceptionThrown":
            errs.append(str(r["params"]["exceptionDetails"].get("exception",{}).get("description"))[:200])
        if r.get("id") == n[0]: return r.get("result", {})
def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:200]
    return r.get("result", {}).get("value")
try:
    cmd("Page.enable"); cmd("Runtime.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"): break
        time.sleep(1)
    ev("document.querySelectorAll('.row')[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2})); 'ok'")
    time.sleep(8)
    print("有当前曲:", ev("!!document.querySelector('.pc img')"))
    print("FullPlayer 组件是否挂载（找 .fp）:", ev("!!document.querySelector('.fp')"))
    print("播放条上 .pc 的 class:", ev("document.querySelector('.pc')?.className"))
    print("点击 .pc ...")
    ev("document.querySelector('.pc').click(); 'ok'")
    time.sleep(2)
    print("  点击后 showFull:", ev("""(function(){var p=document.getElementById('app').__vue_app__
        .config.globalProperties.$pinia.state.value.player; return p.showFull;})()"""))
    print("  .fp 出现:", ev("!!document.querySelector('.fp')"))
    print("  强制设 true ...")
    ev("""(function(){document.getElementById('app').__vue_app__.config.globalProperties.$pinia
        .state.value.player.showFull = true; return 'ok';})()""")
    time.sleep(2)
    print("  .fp 出现:", ev("!!document.querySelector('.fp')"))
    print("  歌词行数:", ev("document.querySelectorAll('.fp .ln').length"))
    print("\n异常:", errs[-3:] if errs else "无")
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
