#!/usr/bin/env python3
"""排查新前端歌单页为何不渲染"""
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9441
prof = tempfile.mkdtemp(prefix="rm-dbg-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + prof, "--no-first-run", "--remote-allow-origins=*",
    "--window-size=1440,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws_url = None
for _ in range(40):
    try:
        for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
            if t.get("type") == "page": ws_url = t["webSocketDebuggerUrl"]; break
        if ws_url: break
    except Exception: pass
    time.sleep(0.5)
ws = websocket.create_connection(ws_url, timeout=90, max_size=32*1024*1024)
n = [0]; msgs = []
def cmd(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("method") == "Runtime.consoleAPICalled":
            msgs.append("CONSOLE " + str(r["params"].get("args", [{}])[0].get("value"))[:150])
        if r.get("method") == "Runtime.exceptionThrown":
            msgs.append("EXCEPTION " + str(r["params"]["exceptionDetails"].get("exception", {}).get("description"))[:200])
        if r.get("method") == "Log.entryAdded":
            e = r["params"]["entry"]
            if e.get("level") in ("error", "warning"):
                msgs.append("LOG[%s] %s %s" % (e.get("level"), e.get("text")[:90], (e.get("url") or "")[-50:]))
        if r.get("id") == n[0]: return r.get("result", {})
def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:200]
    return r.get("result", {}).get("value")
try:
    cmd("Page.enable"); cmd("Runtime.enable"); cmd("Log.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/playlist/24381616")
    time.sleep(10)
    print("h1:", ev("document.querySelector('h1')?.textContent"))
    print("#app 子节点:", ev("document.getElementById('app').children.length"))
    print("页面文字前 200:", (ev("document.body.innerText") or "")[:200].replace("\n", " | "))
    print("\n=== 直接在前端上下文里调接口")
    print(ev("""(async()=>{try{const r=await fetch('/api/playlist/detail?id=24381616');
        const j=await r.json(); return 'HTTP '+r.status+' name='+(j.playlist&&j.playlist.name);}
        catch(e){return 'ERR '+e.message}})()"""))
    print("\n=== 控制台/网络问题")
    for m in msgs[-14:]: print("   ", m)
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
