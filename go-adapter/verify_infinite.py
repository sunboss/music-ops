#!/usr/bin/env python3
"""专测无限电台：真实点击歌单里最后一首 -> 队列见底 -> AI 应自动续歌"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9455
LAN = "http://192.168.1.174:5199"
prof = tempfile.mkdtemp(prefix="rm-inf-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required",
                         "--window-size=1440,900", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws_url = None
for _ in range(40):
    try:
        for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
            if t.get("type") == "page":
                ws_url = t["webSocketDebuggerUrl"]; break
        if ws_url: break
    except Exception: pass
    time.sleep(0.5)
ws = websocket.create_connection(ws_url, timeout=180, max_size=64 * 1024 * 1024)
n = [0]


def cmd(m, **p):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]:
            return r.get("result", {})


def ev(e):
    r = cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r:
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:160]
    return r.get("result", {}).get("value")


def dblclick(sel):
    # 先把元素滚进可视区，否则在视口外的行点击会落空
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;"
           "e.scrollIntoView({block:'center'});"
           "var r=e.getBoundingClientRect();"
           "return JSON.stringify({x:r.left+120,y:r.top+r.height/2});})()" % sel)
    if not b or b == "null":
        return "无此元素 " + sel
    c = json.loads(b)
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=ct)
        time.sleep(0.05)
    return "已双击 " + sel


# 注意：Pinia 的 state 对象上没有 actions，要用 store 实例（$pinia._s.get）
ST = """(function(){var st=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia._s.get('player');return JSON.stringify({cur:st.queue[st.index]?st.queue[st.index].name:null,
    n:st.queue.length, i:st.index, playing:st.playing, prog:+st.progress.toFixed(1),
    auto:st.autoContinue, cont:st.continuing, err:st.error});})()"""

try:
    cmd("Page.enable")
    cmd("Page.navigate", url=LAN + "/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"):
            break
        time.sleep(1)
    # 只取前 3 首播（避免 1000 首队列），再点最后一首触发见底
    dblclick(".row:nth-child(1)")
    time.sleep(6)
    print("起播:", ev(ST))
    # 用 UI 把队列缩短：直接点第 3 首（index 2），队列仍是 1000 —— 所以改用 AI 电台的 15 首队列
    cmd("Page.navigate", url=LAN + "/ai")
    time.sleep(5)
    print("无限电台开关:", json.loads(ev(ST))["auto"])
    # 用场景生成 15 首的电台
    b = ev("(function(){var e=document.querySelector('.chips button');var r=e.getBoundingClientRect();"
           "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()")
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    for _ in range(45):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["n"] > 0 and st["playing"]:
            break
    print("电台就绪:", ev(ST))
    n0 = st["n"]

    print("\n--- 真实双击列表最后一首（让队列见底）")
    print(dblclick(".list .row:last-child"))
    time.sleep(8)
    grew = False
    for i in range(45):
        time.sleep(2)
        st1 = json.loads(ev(ST))
        if st1["n"] > n0:
            grew = True
            break
    print("队列: %d -> %d 首  %s" % (n0, st1["n"], "✓ AI 自动续上了" if grew else "✗ 未续"))
    print("当前:", st1["cur"], "| index:", st1["i"], "| continuing:", st1["cont"], "| err:", st1["err"])
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
