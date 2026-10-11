#!/usr/bin/env python3
"""探查 YesPlayMusic 运行时 store，找出「播放一首歌」的真实入口，用于在真实播放器上验证"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9421

prof = tempfile.mkdtemp(prefix="rm-store-")
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

ws = websocket.create_connection(ws_url, timeout=60, max_size=64 * 1024 * 1024)
n = [0]


def cmd(method, **params):
    n[0] += 1
    ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == n[0]:
            return m.get("result", {})


def ev(expr, awaitp=True):
    r = cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=awaitp)
    if "exceptionDetails" in r:
        return {"__err__": str(r["exceptionDetails"].get("exception", {}).get("description"))[:300]}
    return r.get("result", {}).get("value")


try:
    cmd("Page.enable")
    cmd("Page.navigate", url="https://music.1234r.com")
    time.sleep(9)

    print("Vue 根实例:", ev("!!document.querySelector('#app').__vue__"))
    print("$player 是否存在:", ev("!!document.querySelector('#app').__vue__.$player"))
    print("$player 方法:", ev("""(() => { const p=document.querySelector('#app').__vue__.$player;
      if(!p) return '无';
      const own=[], proto=Object.getPrototypeOf(p);
      Object.getOwnPropertyNames(proto).forEach(k=>own.push(k));
      return JSON.stringify(own.filter(k=>typeof p[k]==='function')); })()"""))
    print("$player 字段:", ev("""(() => { const p=document.querySelector('#app').__vue__.$player;
      if(!p) return '无';
      return JSON.stringify(Object.keys(p)); })()"""))
    print("player 相关 action:", ev("""(() => {
      const s = document.querySelector('#app').__vue__.$store;
      return JSON.stringify(Object.keys(s._actions).filter(k => /player|Player|play/i.test(k)));
    })()"""))
    print("player 相关 mutation:", ev("""(() => {
      const s = document.querySelector('#app').__vue__.$store;
      return JSON.stringify(Object.keys(s._mutations).filter(k => /player|Player|play/i.test(k)));
    })()"""))
    print()
    print("尝试用真实播放器播放 同花顺(4872687)：")
    print(ev("""(async () => {
      const vm = document.querySelector('#app').__vue__;
      const p = vm.$player;
      const s = vm.$store;
      if (p && typeof p.replacePlaylist === 'function') {
        const r0 = await fetch('/api/song/detail?ids=4872687').then(x => x.json());
        const song0 = (r0.songs || [])[0];
        if (!song0) return '取歌曲信息失败';
        p.replacePlaylist([song0], 0, 'rm-verify');
        return '已用真实播放器 replacePlaylist 播放 ' + song0.name;
      }
      const r = await fetch('/api/song/detail?ids=4872687').then(x => x.json());
      const song = (r.songs || [])[0];
      if (!song) return '取歌曲信息失败';
      const cand = ['player/addTrackToPlayerList','player/appendTrackToPlayerList',
                    'player/replacePlaylist','player/playTrack','player/play'];
      const used = cand.find(a => s._actions[a]);
      if (!used) return '未找到播放 action，可用: ' + Object.keys(s._actions).filter(k=>k[0]==='p').join(',');
      try { s.dispatch(used, song, {root:true}); } catch (e) { return 'dispatch 异常: ' + e; }
      return '已调用 ' + used;
    })()"""))
    for k in range(6):
        time.sleep(2)
        st = ev("""(() => {
          const vm = document.querySelector('#app').__vue__;
          const ps = (vm.$store.state.player) || {};
          const el = document.querySelector('audio');
          return JSON.stringify({playing: ps.playing, cur: ps.currentTrack && ps.currentTrack.name,
                                 url: (ps.currentTrack && ps.currentTrack.url || '').slice(-40),
                                 t: el ? +el.currentTime.toFixed(1) : null,
                                 d: el ? +(el.duration||0).toFixed(1) : null});
        })()""")
        print("   %2ds: %s" % ((k + 1) * 2, st))
finally:
    try:
        ws.close()
    except Exception:
        pass
    proc.terminate()
    shutil.rmtree(prof, ignore_errors=True)
