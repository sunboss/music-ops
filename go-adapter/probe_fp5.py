#!/usr/bin/env python3
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9448
prof = tempfile.mkdtemp(prefix="rm-fp5-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
    "--user-data-dir=" + prof, "--no-first-run", "--mute-audio", "--remote-allow-origins=*",
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
n = [0]
def cmd(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]: return r.get("result", {})
def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:" + str(r["exceptionDetails"].get("exception",{}).get("description"))[:250]
    return r.get("result", {}).get("value")
try:
    cmd("Page.enable")
    cmd("Page.navigate", url="http://127.0.0.1:5199/")
    time.sleep(7)
    print("播放条 HTML 前 700 字：")
    print(ev("document.querySelector('.bar')?.outerHTML?.slice(0,700)"))
    print("\n播放条 CSS display:", ev("getComputedStyle(document.querySelector('.bar')).display"))
    print("播放条尺寸:", ev("JSON.stringify(document.querySelector('.bar').getBoundingClientRect())"))
    print("\n=== 自建监听测试（排除 Vue 绑定问题）")
    print(ev("""(function(){window.__hit=0;var el=document.querySelector('.meta');
        if(!el) return 'no .meta'; el.addEventListener('click',function(){window.__hit++;});
        el.dispatchEvent(new MouseEvent('click',{bubbles:true})); return 'dispatched, hit='+window.__hit;})()"""))
    print("\n=== 点 .bar 内的 play 按钮看是否触发播放")
    print("store 状态:", ev("""(function(){var s=document.getElementById('app').__vue_app__.config
        .globalProperties.$pinia.state.value.player;return JSON.stringify({q:s.queue.length,full:s.showFull});})()"""))
    print("\n=== 当前构建的 chunk（确认不是旧缓存）")
    print(ev("JSON.stringify(Array.from(document.querySelectorAll('script[src]')).map(s=>s.src.split('/').pop()))"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
