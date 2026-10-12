#!/usr/bin/env python3
"""验收 AI 智能播放系统：统一指令（控制/续播/点歌）+ 无限电台自动续歌"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9454
LAN = "http://192.168.1.174:5199"
prof = tempfile.mkdtemp(prefix="rm-ai2-")
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


def click(sel):
    b = ev("(function(){var e=document.querySelector(%r);if(!e)return null;var r=e.getBoundingClientRect();"
           "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % sel)
    if not b or b == "null":
        return "无此元素 " + sel
    c = json.loads(b)
    cmd("Input.dispatchMouseEvent", type="mouseMoved", x=c["x"], y=c["y"], button="none")
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=c["x"], y=c["y"], button="left", clickCount=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=c["x"], y=c["y"], button="left", clickCount=1)
    return "已点 " + sel


def type_text(t):
    ev("(function(){var i=document.querySelector('.input input')||document.querySelector('input');"
       "i.value=%s;i.dispatchEvent(new Event('input',{bubbles:true}));return 'ok';})()" % json.dumps(t))


ST = """(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia.state.value.player;return JSON.stringify({cur:s.queue[s.index]?s.queue[s.index].name:null,
    n:s.queue.length, i:s.index, playing:s.playing, prog:+s.progress.toFixed(1),
    auto:s.autoContinue, cont:s.continuing});})()"""

try:
    cmd("Page.enable")
    cmd("Page.navigate", url=LAN + "/ai")
    time.sleep(6)
    print("AI 页:", ev("document.querySelector('h1')?.textContent"),
          "| 无限电台默认:", json.loads(ev(ST))["auto"])

    print("\n--- ① 用场景生成歌单（radio）")
    click(".chips button")
    for _ in range(45):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["n"] > 0 and st["playing"]:
            break
    print("   ", ev(ST))
    print("    意图标签:", ev("document.querySelector('.tag')?.textContent"),
          "| 列表行:", ev("document.querySelectorAll('.list .row').length"))

    print("\n--- ② 统一指令：控制播放（下一首）")
    before = json.loads(ev(ST))["cur"]
    type_text("下一首")
    click(".ops .go")
    for _ in range(15):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st["cur"] != before:
            break
    print("    %r -> %r  %s" % (before, st["cur"], "✓ 已切歌" if st["cur"] != before else "✗ 未响应"))
    print("    意图:", ev("document.querySelector('.tag')?.textContent"))

    print("\n--- ③ 无限电台：跳到队列最后一首，看 AI 会不会自动续")
    st0 = json.loads(ev(ST))
    ev("""(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
        .$pinia.state.value.player; s.playAt(s.queue.length-1); return 'ok';})()""")
    time.sleep(4)
    grew = False
    for i in range(40):
        time.sleep(2)
        st1 = json.loads(ev(ST))
        if st1["n"] > st0["n"]:
            grew = True
            break
    print("    队列: %d -> %d 首 %s" % (st0["n"], st1["n"], "✓ AI 自动续上了" if grew else "✗ 未续"))
    print("    当前:", st1["cur"], "| continuing:", st1["cont"])

    print("\n--- ④ 音乐库（应无登录墙，直接出内容）")
    cmd("Page.navigate", url=LAN + "/library")
    time.sleep(6)
    print("    标题:", ev("document.querySelector('h1')?.textContent"),
          "| Tab:", ev("Array.from(document.querySelectorAll('.tabs button')).map(b=>b.textContent.trim()).join('/')"),
          "| 有内容:", ev("document.querySelectorAll('.row').length"),
          "| 出现登录墙:", ev("!!document.querySelector('.need-login')"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
