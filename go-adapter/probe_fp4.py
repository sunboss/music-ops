#!/usr/bin/env python3
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9447
prof = tempfile.mkdtemp(prefix="rm-fp4-")
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
SF = """(function(){return document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia.state.value.player.showFull;})()"""
try:
    cmd("Page.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"): break
        time.sleep(1)
    ev("document.querySelectorAll('.row')[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2})); 'ok'")
    for i in range(40):
        time.sleep(2)
        if ev("!!document.querySelector('.pc img')"): break
    print("播放条就绪, showFull=", ev(SF))
    print(".pc 元素:", ev("document.querySelector('.pc')?.tagName + ' / ' + document.querySelector('.pc')?.className"))
    print(".meta 元素:", ev("document.querySelector('.meta')?.tagName + ' / ' + document.querySelector('.meta')?.className"))
    print("\n--- 点 .meta")
    ev("document.querySelector('.meta').click(); 'ok'")
    time.sleep(1.5)
    print("   showFull=", ev(SF), " .fp=", ev("!!document.querySelector('.fp')"))
    print("\n--- 直接派发 click 到 .pc")
    ev("""(function(){var el=document.querySelector('.pc');
        el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));return 'ok';})()""")
    time.sleep(1.5)
    print("   showFull=", ev(SF), " .fp=", ev("!!document.querySelector('.fp')"))
    print("\n--- 直接改 store 再渲染")
    ev("""(function(){document.getElementById('app').__vue_app__.config.globalProperties.$pinia
        .state.value.player.showFull=true;return 'ok';})()""")
    time.sleep(1.5)
    print("   showFull=", ev(SF), " .fp=", ev("!!document.querySelector('.fp')"),
          " 歌词=", ev("document.querySelectorAll('.fp .ln').length"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
