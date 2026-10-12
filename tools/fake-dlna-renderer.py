#!/usr/bin/env python3
"""假 DLNA 渲染器：只用于验证 tools/dlna-bridge.py 的发现与投屏代码路径。

本网络里没有真正的 DLNA 渲染器（192.168.1.158 是华为网关，/upnpap.xml 返回 403），
所以起一个最小的 MediaRenderer 模拟器：回应 SSDP M-SEARCH + 提供设备描述 + 接收
AVTransport 指令，把收到的 SetAVTransportURI/Play/Stop 打印出来。
"""
from __future__ import annotations

import http.server
import re
import socket
import socketserver
import sys
import threading
import time

PORT = 8790
IP = "192.168.1.174"
NAME = "测试渲染器 (fake DLNA)"

DEVICE_XML = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>{name}</friendlyName>
    <manufacturer>r-music-test</manufacturer>
    <modelName>FakeRenderer</modelName>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
        <controlURL>/control</controlURL>
        <eventSubURL>/event</eventSubURL>
        <SCPDURL>/AVTransport.xml</SCPDURL>
      </service>
    </serviceList>
  </device>
</root>
""".format(name=NAME)

RECEIVED: list[str] = []


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):  # 静音
        pass

    def do_GET(self):
        if self.path.startswith("/device.xml"):
            body = DEVICE_XML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "ignore")
        action = (self.headers.get("SOAPAction") or "").strip('"').split("#")[-1]
        uri = re.search(r"<CurrentURI>(.*?)</CurrentURI>", body)
        RECEIVED.append(f"{action} {uri.group(1) if uri else ''}")
        print("[fake-renderer] 收到指令:", RECEIVED[-1], flush=True)
        resp = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                "<s:Body><u:%sResponse xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\"/>"
                "</s:Body></s:Envelope>" % action).encode()
        self.send_response(200)
        self.send_header("Content-Type", 'text/xml; charset="utf-8"')
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def ssdp_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    s.bind(("", 1900))
    mreq = socket.inet_aton("239.255.255.250") + socket.inet_aton("0.0.0.0")
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.settimeout(1)
    print("[fake-renderer] SSDP 监听 1900", flush=True)
    while True:
        try:
            data, addr = s.recvfrom(65507)
        except socket.timeout:
            continue
        except OSError:
            break
        text = data.decode("utf-8", "ignore")
        if "M-SEARCH" not in text:
            continue
        st = re.search(r"(?im)^ST:\s*(.+)$", text)
        st = st.group(1).strip() if st else "ssdp:all"
        if not (st == "ssdp:all" or "MediaRenderer" in st or "AVTransport" in st):
            continue
        print("[fake-renderer] 收到 M-SEARCH ST=%s，回包" % st, flush=True)
        reply = ("HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\nEXT:\r\n"
                 "LOCATION: http://%s:%d/device.xml\r\n"
                 "SERVER: fake/1.0 UPnP/1.0\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
                 "USN: uuid:fake-renderer::urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n"
                 % (IP, PORT)).encode()
        s.sendto(reply, addr)


if __name__ == "__main__":
    threading.Thread(target=ssdp_loop, daemon=True).start()
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
    print("[fake-renderer] HTTP :%d device.xml" % PORT, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
