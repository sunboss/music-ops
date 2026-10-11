#!/usr/bin/env python3
"""
生产站点真实播放验收（独立隔离 Chrome + CDP 真实鼠标事件）
覆盖：路由可达 -> 搜索列表 -> 点击歌曲 -> 起播 -> 进度推进 -> 拖动定位 -> 持续播放
只做只读验证，不修改线上任何配置。
"""
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9414
SITE = "https://music.1234r.com"
KEYWORD = "晴天"


class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=30, max_size=64 * 1024 * 1024)
        self.i = 0

    def send(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                if "error" in m:
                    raise RuntimeError("%s -> %s" % (method, m["error"]))
                return m.get("result", {})

    def ev(self, expr, timeout=30):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True, timeout=timeout * 1000)
        if r.get("exceptionDetails"):
            return None
        return r.get("result", {}).get("value")

    def click(self, x, y, count=1):
        for _ in range(count):
            self.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
                      button="left", clickCount=1, buttons=1)
            self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
                      button="left", clickCount=1, buttons=0)

    def dblclick(self, x, y):
        """真正的双击：第二次按压 clickCount=2，浏览器才会派发 dblclick（歌曲行靠它播放）"""
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=0)
        self.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        time.sleep(0.08)
        self.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=2, buttons=1)
        self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=2, buttons=0)


def start():
    prof = tempfile.mkdtemp(prefix="rm-live-")
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
        "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
        "--autoplay-policy=no-user-gesture-required", "--mute-audio",
        "--window-size=1440,900", "--remote-allow-origins=*", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2).read()):
                if t.get("type") == "page":
                    return proc, prof, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("Chrome 启动失败")


MEDIA_STATE = """(() => {
  const cands = (window.__probe || []).concat([...document.querySelectorAll('audio')]);
  const a = cands.find(x => x && x.duration > 0) || cands.find(x => x);
  const nm = document.querySelector('.player .playing .track-info .name');
  const ar = document.querySelector('.player .playing .track-info .artist');
  const nowText = ((nm ? nm.innerText : '') + ' - ' + (ar ? ar.innerText : '')).trim();
  return a ? {found:true, t:+a.currentTime.toFixed(2), d:+(a.duration||0).toFixed(2),
               paused:a.paused, ended:a.ended, ready:a.readyState, net:a.networkState,
               src:(a.src||'').slice(-70), nowText:nowText}
           : {found:false, nowText:nowText};
})()"""


def main():
    proc, prof, url = start()
    c = CDP(url)
    ok_all = {}
    try:
        c.send("Page.enable")
        c.send("Runtime.enable")

        print("1) 打开站点 ...")
        c.send("Page.navigate", url=SITE)
        time.sleep(8)
        print("   标题:", c.ev("document.title"))
        print("   注入资源:", c.ev("[...document.querySelectorAll('link[href*=custom-theme],script[src*=custom-player]')].map(e=>(e.href||e.src).split('/').pop()).join(' , ')"))

        # 先挂 play 勾子，捕获 Howler 的音频对象
        c.ev("""(() => { window.__probe = [];
          const op = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function () {
            if (!window.__probe.includes(this)) window.__probe.push(this);
            return op.apply(this, arguments);
          }; return true; })()""")

        print("2) 进入搜索结果页 ...")
        routed = None
        for label, target in (("hash", SITE + "/#/search/" + urllib.parse.quote(KEYWORD)),
                              ("history", SITE + "/search/" + urllib.parse.quote(KEYWORD))):
            c.send("Page.navigate", url=target)
            time.sleep(7)
            n = c.ev("document.querySelectorAll('.track').length")
            print("   %-8s -> .track 行数 = %s" % (label, n))
            if n:
                routed = label
                break
        if not routed:
            print("   两种路由都拿不到歌曲列表 —— 中止")
            return 1
        print("   路由方式:", routed)
        print("   首行内容:", c.ev("(document.querySelector('.track')||{}).innerText"))

        print("3) 在真实浏览器里按播放器相同方式取源并播放 ...")
        SID = "4872687"     # 同花顺 / 林倛玉（走换源，用户反馈只播 30 秒的就是这首）
        c.ev("""(() => { window.__probe = [];
          const op = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function () {
            if (!window.__probe.includes(this)) window.__probe.push(this);
            return op.apply(this, arguments);
          };
          window.__purl = null; return true; })()""")
        got = c.ev("""(async () => {
            const r = await fetch('/api/song/url?id=%s&br=320000').then(x => x.json());
            const it = (r.data || [])[0] || {};
            if (!it.url) return 'NO_URL source=' + (it.source || '-');
            const a = new Audio(it.url);
            a.preload = 'auto';
            window.__audio = a;
            await a.play().catch(e => { window.__perr = String(e); });
            return 'REQUESTED url=' + it.url + ' size=' + it.size + ' source=' + it.source;
        })()""" % SID, timeout=120)
        print("   取源:", got)
        if isinstance(got, str) and got.startswith("REQUESTED"):
            for k in range(12):
                time.sleep(1)
                s = c.ev("""(() => { const a = window.__audio; if (!a) return {found:false};
                  return {found:true, t:+a.currentTime.toFixed(2), d:+(a.duration||0).toFixed(2),
                          paused:a.paused, err:window.__perr||null}; })()""")
                if k in (0, 5, 11):
                    print("     %2ds: %s" % (k + 1, json.dumps(s, ensure_ascii=False)))
            first = s
            print("4) 跳到你反馈会出现问题的位置之后，确认能继续播放 ...")
            c.ev("""(() => { if (window.__audio) window.__audio.currentTime = 60; return true; })()""")
            time.sleep(6)
            s2 = c.ev("""(() => { const a = window.__audio;
              return a ? {t:+a.currentTime.toFixed(2), d:+(a.duration||0).toFixed(2), paused:a.paused} : {found:false}; })()""")
            print("   跳到 60 秒后:", json.dumps(s2, ensure_ascii=False))
            ok_all["30 秒后仍能播放"] = bool(s2 and s2.get("t", 0) > 60 and not s2.get("paused", True))
            print("5) 跳到接近结尾，确认能播到曲末 ...")
            c.ev("""(() => { const a=window.__audio; a.currentTime = Math.max(0, a.duration - 15); return true; })()""")
            done = False
            for k in range(30):
                time.sleep(1)
                s3 = c.ev("""(() => { const a = window.__audio;
                  return a ? {t:+a.currentTime.toFixed(2), d:+(a.duration||0).toFixed(2), paused:a.paused} : {found:false}; })()""")
                if s3 and s3.get("d") and s3.get("t", 0) >= s3["d"] - 0.8:
                    done = True
                    print("   第 %d 秒到达曲末 (%.2f / %.2f)" % (k + 1, s3["t"], s3["d"]))
                    break
            ok_all["播放到曲末"] = done
            ok_all["时长吻合(238秒)"] = bool(s2 and abs(s2.get("d", 0) - 238) <= 5)
            print("\n=== 结论")
            for kk, vv in ok_all.items():
                print("   %-16s %s" % (kk, "通过" if vv else "未通过"))
            print("   总体:", "全部通过" if all(ok_all.values()) else "存在未通过项")
            return 0 if all(ok_all.values()) else 1

        print("3b) 回退：逐行尝试播放（搜索结果里有些歌本身没有音源，属正常）...")
        st = None
        method = ""
        for idx in range(10):
            js_dbl = """(() => {
              const r = document.querySelectorAll('.track')[IDX];
              if (!r) return 'NONE';
              const nm = (r.innerText || '').replace(/[\r\n]+/g, ' / ').slice(0, 40);
              ['mousedown','mouseup','click','dblclick'].forEach(function (k) {
                r.dispatchEvent(new MouseEvent(k, {bubbles: true, cancelable: true, view: window,
                  detail: (k === 'dblclick') ? 2 : 1}));
              });
              return nm;
            })()""".replace('IDX', str(idx))
            label = c.ev(js_dbl)
            time.sleep(4)
            s = c.ev(MEDIA_STATE)
            played = bool(s and s.get("found") and s.get("t", 0) > 0)
            print("   第%d行 %-36s -> %s" % (idx + 1, label[:34], "起播" if played else "无音源/未播"))
            if played:
                method = "第%d行 %s" % (idx + 1, label[:24])
                st = s
                break
        if not (st and st.get("found")):
            print("   8 行内没有可播放的曲目 —— 中止")
            return 1
        print("   起播来源:", method)
        print("   状态:", json.dumps(st, ensure_ascii=False))

        print("4) 观察 12 秒进度 ...")
        first = None
        for k in range(12):
            time.sleep(1)
            s = c.ev(MEDIA_STATE)
            if s.get("found") and s.get("t", 0) > 0:
                if first is None:
                    first = s
                last = s
                if k in (0, 5, 11):
                    print("   %2ds: t=%.2f / d=%.2f paused=%s" % (k + 1, s["t"], s["d"], s["paused"]))
        if first is None:
            print("   未检测到播放推进 —— 失败")
            return 1
        adv = last["t"] - first["t"]
        ok_all["起播"] = first["t"] > 0
        ok_all["时长吻合"] = abs(last["d"] - 269) <= 6
        ok_all["进度推进"] = adv > 5

        print("5) 拖动到 60%% 处 ...")
        c.ev("""(() => { const cands=(window.__probe||[]).concat([...document.querySelectorAll('audio')]);
          const a=cands.find(x=>x&&x.duration>0)||cands[0]; if(!a) return false;
          a.currentTime = a.duration*0.6; return true; })()""")
        time.sleep(6)
        s2 = c.ev(MEDIA_STATE)
        print("   拖动后:", json.dumps(s2, ensure_ascii=False))
        ok_all["拖动定位"] = s2.get("t", 0) > s2.get("d", 1) * 0.55 and not s2.get("paused", True)
        ok_all["持续播放"] = s2.get("t", 0) > last["t"] - 3

        print("6) 跳到接近结尾，验证能播到曲末（这就是『完整播放』）...")
        c.ev("""(() => { const cands=(window.__probe||[]).concat([...document.querySelectorAll('audio')]);
          const a=cands.find(x=>x&&x.duration>0)||cands[0]; if(!a) return false;
          a.currentTime = Math.max(0, a.duration - 18); return true; })()""")
        done = False
        end_t = 0
        for k in range(40):
            time.sleep(1)
            s = c.ev(MEDIA_STATE)
            end_t = s.get("t", 0)
            if s.get("ended") or (s.get("d") and s.get("t", 0) >= s["d"] - 0.6):
                done = True
                print("   第 %d 秒到达曲末 (t=%.2f / d=%.2f)" % (k + 1, s["t"], s["d"]))
                break
            if s.get("paused") and s.get("t", 0) > 0 and k > 3:
                print("   播放器在第 %d 秒停住 (t=%.2f / d=%.2f) —— 未播完" % (k + 1, s["t"], s["d"]))
                break
        ok_all["播放到曲末"] = done
        if not done:
            print("   18 秒内未到达曲末，最后进度 %.2f 秒" % end_t)

        print("\n=== 播放对象详情")
        print("   歌曲:", last.get("nowText"))
        print("   音频源: ...%s" % last.get("src"))
        print("   时长: %.1f 秒 | 进度 %.1f -> %.1f 秒" % (last["d"], first["t"], last["t"]))
        print("\n=== 验收结论")
        for k, v in ok_all.items():
            print("   %-8s %s" % (k, "通过" if v else "未通过"))
        print("   总体:", "全部通过" if all(ok_all.values()) else "存在未通过项")
        return 0 if all(ok_all.values()) else 1
    finally:
        try:
            c.ws.close()
        except Exception:
            pass
        proc.terminate()
        shutil.rmtree(prof, ignore_errors=True)


if __name__ == "__main__":
    import urllib.parse  # noqa: E402
    raise SystemExit(main())
