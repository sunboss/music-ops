#!/usr/bin/env python3
"""DLNA/UPnP 投屏小桥 —— 给浏览器当"本机发现代理"。

为什么需要它：浏览器不能发 SSDP 组播，所以 DLNA 设备在一个纯网页里是发现不了的。
这个小桥跑在**打开网页的那台设备本机**（127.0.0.1），由它做发现并代为下发 AVTransport 指令；
音频直链是公网的，DLNA 渲染器自己去取流。

用法：
    python3 tools/dlna-bridge.py            # 监听 127.0.0.1:8787
    python3 tools/dlna-bridge.py --port 8788

网页侧会自动探测 http://127.0.0.1:8787/health，没启动就提示启动命令，不假装有设备。
"""
from __future__ import annotations

import argparse
import http.server
import json
import re
import socket
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

PORT = 8787
ALLOW_ORIGIN = "*"
SOAP_ENV = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>%s</s:Body></s:Envelope>'


def log(*a):
    print("[dlna-bridge]", *a, flush=True)


# ------------------------------------------------------------------ SSDP 发现
def ssdp_search(st: str, timeout: float = 3.0) -> list[str]:
    msg = ('M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:"ssdp:discover"\r\n'
           "MX:2\r\nST:%s\r\n\r\n" % st).encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(1)
    locs = []
    try:
        s.sendto(msg, ("239.255.255.250", 1900))
    except OSError as e:
        log("SSDP 发包失败:", e)
        s.close()
        return locs
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            data, _ = s.recvfrom(65507)
        except socket.timeout:
            continue
        except OSError:
            break
        text = data.decode("utf-8", "ignore")
        m = re.search(r"(?im)^location:\s*(\S+)", text)
        if m and m.group(1) not in locs:
            locs.append(m.group(1))
    s.close()
    return locs


NS = {
    "d": "urn:schemas-upnp-org:device-1-0",
    "s": "urn:schemas-upnp-org:service-1-0",
}


def describe(location: str) -> dict | None:
    """取设备描述，拿到名字与 AVTransport 控制地址"""
    try:
        with urllib.request.urlopen(location, timeout=5) as r:
            xml = r.read()
    except Exception as e:
        log("取设备描述失败 %s: %s" % (location, str(e)[:60]))
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    dev = root.find("d:device", NS)
    if dev is None:
        return None
    name = (dev.findtext("d:friendlyName", "", NS) or "").strip()
    control, service_type = "", ""
    for svc in dev.findall(".//d:serviceList/d:service", NS):
        stype = svc.findtext("d:serviceType", "", NS) or ""
        if "AVTransport" in stype:
            ctl = (svc.findtext("d:controlURL", "", NS) or "").strip()
            base = re.match(r"(https?://[^/]+)", location)
            control = (base.group(1) + ctl) if (base and ctl.startswith("/")) else (ctl or location)
            service_type = stype
            break
    if not control:
        return None
    ip = re.match(r"https?://([^:/]+)", location)
    return {"name": name or "DLNA 设备", "ip": ip.group(1) if ip else location,
            "control": control, "type": service_type, "location": location}


def discover() -> list[dict]:
    found, seen = [], set()
    for st in ("urn:schemas-upnp-org:device:MediaRenderer:1", "ssdp:all"):
        for loc in ssdp_search(st):
            if loc in seen:
                continue
            seen.add(loc)
            d = describe(loc)
            if d:
                found.append(d)
    return found


# ------------------------------------------------------------------ AVTransport
def soap(control: str, action: str, inner: str, timeout: float = 6.0) -> tuple[bool, str]:
    body = SOAP_ENV % inner
    req = urllib.request.Request(control, data=body.encode(), headers={
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": '"urn:schemas-upnp-org:service:AVTransport:1#%s"' % action,
        "User-Agent": "r-music-dlna-bridge/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300, r.read(400).decode("utf-8", "ignore")
    except Exception as e:
        return False, str(e)[:200]


def didl(url: str, title: str = "") -> str:
    t = (title or "R-Music").replace("&", "&amp;").replace("<", "&lt;")
    return ('&lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;'
            "&lt;item id=\"0\" parentID=\"-1\" restricted=\"1\"&gt;"
            "&lt;dc:title&gt;%s&lt;/dc:title&gt;"
            "&lt;upnp:class&gt;object.item.audioItem.musicTrack&lt;/upnp:class&gt;"
            "&lt;res protocolInfo=\"http-get:*:audio/mpeg:*\"&gt;%s&lt;/res&gt;"
            "&lt;/item&gt;&lt;/DIDL-Lite&gt;" % (t, url))


def play(control: str, url: str, title: str = "") -> tuple[bool, str]:
    inner = ('<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
             "<InstanceID>0</InstanceID><CurrentURI>%s</CurrentURI>"
             "<CurrentURIMetaData>%s</CurrentURIMetaData></u:SetAVTransportURI>") % (url, didl(url, title))
    ok, msg = soap(control, "SetAVTransportURI", inner)
    if not ok:
        return False, "SetAVTransportURI 失败: " + msg
    inner2 = ('<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
              "<InstanceID>0</InstanceID><Speed>1</Speed></u:Play>")
    ok2, msg2 = soap(control, "Play", inner2)
    return ok2, "" if ok2 else "Play 失败: " + msg2


def stop(control: str) -> tuple[bool, str]:
    inner = ('<u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
             "<InstanceID>0</InstanceID></u:Stop>")
    return soap(control, "Stop", inner)


# ------------------------------------------------------------------ HTTP
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code: int, data, ctype="application/json;charset=utf-8"):
        if not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        # Chrome 的私有网络访问限制：公网 HTTPS 页面访问 127.0.0.1 时，
        # 预检必须显式允许，否则请求在浏览器里就被拦掉（桥上看不到任何请求）
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        print("[dlna-bridge] 预检 OPTIONS %s（来自 %s）"
              % (self.path, self.headers.get("Origin") or "-"), flush=True)
        self._send(204, b"")

    def do_GET(self):
        print("[dlna-bridge] GET %s（来自 %s）" % (self.path, self.headers.get("Origin") or "-"), flush=True)
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True, "name": "r-music-dlna-bridge", "port": PORT})
        if self.path.startswith("/devices"):
            devs = discover()
            log("发现 %d 台 DLNA 渲染器" % len(devs))
            return self._send(200, {"devices": devs})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        if self.path.startswith("/cast"):
            url, ctl = body.get("url") or "", body.get("control") or ""
            if not url or not ctl:
                return self._send(400, {"error": "缺少 url 或 control"})
            ok, msg = play(ctl, url, body.get("title") or "")
            log("投屏 %s -> %s" % (url[:60], "成功" if ok else msg))
            return self._send(200 if ok else 502, {"ok": ok, "error": msg})
        if self.path.startswith("/stop"):
            ok, msg = stop(body.get("control") or "")
            return self._send(200 if ok else 502, {"ok": ok, "error": msg})
        self._send(404, {"error": "not found"})


def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    PORT = a.port
    srv = http.server.ThreadingHTTPServer((a.host, PORT), Handler)
    log("已启动 http://%s:%d（只服务本机浏览器；DLNA 渲染器自己取音频流）" % (a.host, PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("退出")


if __name__ == "__main__":
    sys.exit(main())
