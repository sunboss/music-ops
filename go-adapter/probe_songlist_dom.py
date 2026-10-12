#!/usr/bin/env python3
"""看一下搜索结果的真实 DOM，找出可点击的歌曲行"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9428
prof = tempfile.mkdtemp(prefix="rm-dom-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run", "--mute-audio",
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
ws = websocket.create_connection(ws_url, timeout=90, max_size=32 * 1024 * 1024)
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
        return "抛错:" + str(r["exceptionDetails"].get("exception", {}).get("description"))[:150]
    return r.get("result", {}).get("value")

try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com/search/%E5%AF%8C%E5%A3%AB%E5%B1%B1%E4%B8%8B")
    time.sleep(12)
    print("URL:", ev("location.pathname + location.search"))
    print("\n=== 常见列表容器数量")
    print(ev("""JSON.stringify(['.song-list','.list-item','.track','.song','.item','tbody tr',
      '.tracks','.song-list-item','[class*=song]','[class*=track]'].map(function(s){
      try { return s + '=' + document.querySelectorAll(s).length; } catch(e){ return s+'=err'; }
    }))"""))
    print("\n=== 双击事件的宿主元素（找带 dblclick 的）")
    print(ev("""(function(){
      var out=[], els=document.querySelectorAll('div,tr,li');
      for (var i=0;i<els.length && out.length<6;i++){
        var e=els[i];
        if (e.innerText && e.innerText.length>3 && e.innerText.length<120 &&
            /\\d{1,2}:\\d{2}/.test(e.innerText)) { out.push(e.tagName+'.'+(e.className||'').slice(0,60)); }
      }
      return JSON.stringify(out);
    })()"""))
    print("\n=== 页面里的播放相关 URL")
    print(ev("""(function(){
      var out=[], a=document.querySelectorAll('a[href]');
      for (var i=0;i<a.length && out.length<5;i++){
        if (/\\/song|\\/track/.test(a[i].getAttribute('href'))) out.push(a[i].getAttribute('href')+' | '+a[i].innerText.slice(0,20));
      }
      return JSON.stringify(out);
    })()"""))
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate(); shutil.rmtree(prof, ignore_errors=True)
