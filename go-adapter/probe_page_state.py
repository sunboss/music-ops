#!/usr/bin/env python3
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9429
prof = tempfile.mkdtemp(prefix="rm-st-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + prof, "--no-first-run", "--mute-audio", "--remote-allow-origins=*",
    "--window-size=1280,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    cmd("Page.navigate", url="https://music.1234r.com/")
    time.sleep(14)
    print("首页 body 前 300 字:", (ev("document.body.innerText") or "")[:300].replace("\n", " | "))
    print("#app 存在:", ev("!!document.getElementById('app')"))
    print("div 总数:", ev("document.querySelectorAll('div').length"))
    print("\n=== 点开搜索结果页")
    ev("location.hash = '#/search/%E5%AF%8C%E5%A3%AB%E5%B1%B1%E4%B8%8B'; 'ok'")
    time.sleep(8)
    print("body 前 400 字:", (ev("document.body.innerText") or "")[:400].replace("\n", " | "))
    print("\n=== 带 .item 的类名样本")
    print(ev("""JSON.stringify(Array.from(document.querySelectorAll('*'))
        .map(function(e){return e.className}).filter(function(c){return typeof c==='string' && c})
        .reduce(function(a,c){ if(a.indexOf(c)<0) a.push(c); return a; },[]).slice(0,25))"""))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
