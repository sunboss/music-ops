#!/usr/bin/env python3
"""和用户手机环境一致：从局域网地址打开新前端，真实点击播放，验证音频真的在走"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9451
LAN = "http://192.168.1.174:5199"      # 与手机访问完全相同的地址
prof = tempfile.mkdtemp(prefix="rm-lan-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--autoplay-policy=no-user-gesture-required",
                         "--remote-allow-origins=*", "--window-size=390,844", "about:blank"],
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
ws = websocket.create_connection(ws_url, timeout=120, max_size=64 * 1024 * 1024)
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


# 注意：本站的 <audio> 是程序创建的单例，没有插入 DOM，querySelector('audio') 取不到；
# 判定「真的在播」要看 store 里的 progress（由真实 timeupdate 事件驱动）
ST = """(function(){var s=document.getElementById('app').__vue_app__.config.globalProperties
    .$pinia.state.value.player;
    return JSON.stringify({cur:s.queue[s.index]?s.queue[s.index].name:null, playing:s.playing,
      loading:s.loading, err:s.error, progress:+s.progress.toFixed(1), duration:s.duration});})()"""

try:
    cmd("Page.enable")
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    cmd("Page.navigate", url=LAN + "/playlist/24381616")
    for _ in range(40):
        if ev("document.querySelectorAll('.row').length>5"):
            break
        time.sleep(1)
    print("页面:", ev("location.href"))
    print("曲目行:", ev("document.querySelectorAll('.row').length"))

    b = json.loads(ev("(function(){var e=document.querySelectorAll('.row')[0];var r=e.getBoundingClientRect();"
                      "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()"))
    for ct in (1, 2):
        cmd("Input.dispatchMouseEvent", type="mousePressed", x=b["x"], y=b["y"], button="left", clickCount=ct)
        cmd("Input.dispatchMouseEvent", type="mouseReleased", x=b["x"], y=b["y"], button="left", clickCount=ct)
        time.sleep(0.05)
    print("已真实双击第一首")

    seen = None
    for i in range(30):
        time.sleep(2)
        st = json.loads(ev(ST))
        if st.get("progress", 0) > 2:
            seen = st
            break
        if st["err"]:
            seen = st
            break
    print("播放状态:", json.dumps(seen, ensure_ascii=False) if seen else ev(ST))
    if seen and seen.get("progress", 0) > 2:
        print("\n✅ 结论文一：store 进度在推进（已播 %.1f 秒 / 共 %s 秒）" % (seen["progress"], seen.get("duration")))
    else:
        print("\n❌ 结论：没有真正播放")
    # 用页面上下文直接取音频地址并发起请求，看是否 200（等价于播放器拿到的资源）
    print("音频资源可达性:", ev("""(async()=>{try{
        const u='/api/audio/proxy?id='+document.getElementById('app').__vue_app__.config
          .globalProperties.$pinia.state.value.player.queue[0].id;
        const r=await fetch(u,{headers:{Range:'bytes=0-1023'}});
        return 'HTTP '+r.status+' '+(await r.arrayBuffer()).byteLength+' 字节';
      }catch(e){return 'ERR '+e.message}})()"""))
    # 再等几秒看进度是否推进
    t1 = json.loads(ev(ST))["progress"]
    time.sleep(5)
    t2 = json.loads(ev(ST))["progress"]
    print("进度推进检查: %.1f -> %.1f 秒（%s）" % (t1, t2, "✓ 真的在播" if t2 > t1 else "✗ 卡住"))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
