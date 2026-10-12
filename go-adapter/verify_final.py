#!/usr/bin/env python3
"""最终确认：生产站真实起播 + 队列交接（用当前线上构建）"""
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9460; SITE = "https://music.1234r.com"
prof = tempfile.mkdtemp(prefix="rm-fin-")
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
ws = websocket.create_connection(ws_url, timeout=180, max_size=64*1024*1024)
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
def dbl(sel, dx=120):
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;e.scrollIntoView({block:'center'});"
           "var r=e.getBoundingClientRect();return JSON.stringify({x:r.left+%d,y:r.top+r.height/2});})()" % (sel, dx))
    if not b or b == "null": return "无此元素 " + sel
    c = json.loads(b)
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=ct)
        time.sleep(0.06)
    return "ok"
ST = """(function(){var st=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia._s.get('player');return JSON.stringify({cur:st.queue[st.index]?st.queue[st.index].name:null,
    n:st.queue.length,i:st.index,playing:st.playing,prog:+st.progress.toFixed(1),dur:st.duration,err:st.error});})()"""
try:
    cmd("Page.enable")
    cmd("Page.navigate", url=SITE + "/playlist/24381616")
    for _ in range(30):
        time.sleep(2)
        if (ev("document.querySelectorAll('.row').length") or 0) > 0: break
    print("歌单页行数:", ev("document.querySelectorAll('.row').length"))
    # 注意：不能用 .row:nth-child(1)——虚拟滚动的首个子元素是占位层，匹配不到任何行
    print("  ", dbl(".row"))
    for _ in range(40):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["prog"] > 2 and st["playing"]: break
    a = st["prog"]; time.sleep(12); st2 = json.loads(ev(ST))
    print("正在播: %s | %.1fs -> %.1fs %s | 时长 %.0fs | err=%r"
          % (st2["cur"], a, st2["prog"], "✓ 持续推进" if st2["prog"] > a + 4 else "✗ 停住", st2["dur"], st2["err"]))
    print("队列:", st2["n"], "首 | index:", st2["i"], "| 无限电台:", json.loads(ev(ST))["n"] >= 0)
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
