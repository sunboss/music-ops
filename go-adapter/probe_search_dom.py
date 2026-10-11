#!/usr/bin/env python3
"""检查搜索页：接口返回是否正确、页面是否渲染出列表"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9417
KW = "晴天"

print("=== 1) 公网接口返回（前 3 首）")
try:
    d = json.loads(urllib.request.urlopen(
        "https://music.1234r.com/api/search?keywords=%s&type=1&limit=3" % urllib.parse.quote(KW),
        timeout=40).read())
    r = d.get("result") or {}
    print("   result 键:", sorted(r.keys())[:10])
    print("   songCount:", r.get("songCount"))
    for s in (r.get("songs") or [])[:3]:
        print("   -", s.get("name"), "|", [a.get("name") for a in (s.get("ar") or [])],
              "| dt=", s.get("dt"), "| al=", (s.get("al") or {}).get("name"))
except Exception as e:
    print("   失败:", e)

prof = tempfile.mkdtemp(prefix="rm-dom-")
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
                         "--user-data-dir=" + prof, "--no-first-run",
                         "--autoplay-policy=no-user-gesture-required", "--mute-audio",
                         "--window-size=1440,900", "--remote-allow-origins=*", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws_url = None
for _ in range(40):
    try:
        for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
            if t.get("type") == "page":
                ws_url = t["webSocketDebuggerUrl"]
                break
        if ws_url:
            break
    except Exception:
        pass
    time.sleep(0.5)

ws = websocket.create_connection(ws_url, timeout=30, max_size=64 * 1024 * 1024)
n = [0]


def ev(expr):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == n[0]:
            res = m.get("result", {})
            if "exceptionDetails" in res:
                return "抛错: " + str(res["exceptionDetails"])[:150]
            return res.get("result", {}).get("value")


try:
    ev("1")
    ev("'page.enable'")
    print()
    print("=== 2) 浏览器里访问搜索页并抓取页面内的接口调用结果")
    ev("""(() => { window.__reqs=[];
      const of=window.fetch;
      window.fetch=function(){ const u=arguments[0]; window.__reqs.push(String(u));
        return of.apply(this,arguments); };
      const ox=XMLHttpRequest.prototype.open;
      XMLHttpRequest.prototype.open=function(m,u){ window.__reqs.push(String(u)); return ox.apply(this,arguments); };
      return true; })()""")
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": "Page.navigate",
                        "url": "https://music.1234r.com/search/" + urllib.parse.quote(KW)}))
    time.sleep(10)
    print("   页面请求过的接口:")
    for u in (ev("JSON.stringify(window.__reqs||[])") or "[]")[:600].split('","'):
        print("     ", u.strip('[]"'))
    print()
    print("=== 3) 页面渲染情况")
    print("   .track 行数:", ev("document.querySelectorAll('.track').length"))
    print("   .track-list:", ev("document.querySelectorAll('.track-list').length"))
    print("   .item 数:", ev("document.querySelectorAll('.item').length"))
    print("   正文前 300 字:", (ev("(document.body.innerText||'').slice(0,300)") or "").replace("\n", " / "))
finally:
    ws.close()
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
