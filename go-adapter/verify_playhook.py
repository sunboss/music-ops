#!/usr/bin/env python3
"""验证「播放回报」：在站点页面里播放一次音频，看服务端能否收到 src + 时长"""
import json, shutil, subprocess, tempfile, time, urllib.request
import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9424
prof = tempfile.mkdtemp(prefix="rm-ph-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
                         "--autoplay-policy=no-user-gesture-required",
                         "--remote-allow-origins=*", "--window-size=1280,900", "about:blank"],
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
ws = websocket.create_connection(ws_url, timeout=60, max_size=64*1024*1024)
n=[0]
def cmd(m, **p):
    n[0]+=1; ws.send(json.dumps({"id":n[0],"method":m,"params":p}))
    while True:
        r=json.loads(ws.recv())
        if r.get("id")==n[0]: return r.get("result",{})
def ev(e):
    r=cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
    if "exceptionDetails" in r: return "抛错:"+str(r["exceptionDetails"])[:150]
    return r.get("result",{}).get("value")
try:
    cmd("Page.enable"); cmd("Page.navigate", url="https://music.1234r.com"); time.sleep(10)
    print("注入版本:", ev("window.__RM_VERSION"))
    # 用与播放器相同的方式（Howler 用的就是 HTMLMediaElement.play）播一次
    print("播放结果:", ev("""(async () => {
      const r = await fetch('/api/song/url?id=4872687&br=320000').then(x=>x.json());
      const u = ((r.data||[])[0]||{}).url;
      if (!u) return '无音源';
      const a = new Audio(u); a.preload='auto'; window.__t = a;
      await a.play().catch(e=>{});
      await new Promise(s=>setTimeout(s,3000));
      return 'playing dur=' + a.duration;
    })()"""))
    time.sleep(3)
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
