#!/usr/bin/env python3
"""验收用的模拟 DLNA 渲染器：真的响应 SSDP，真的收 AVTransport 指令并记录。
用来端到端证明「发现 -> 列表 -> 投屏」这条链路，不需要用户家里真有 DLNA 电视。"""
import http.server, json, os, re, socket, struct, threading, time

PORT = 8899
REC = "/tmp/mock-dlna-received.log"
DESC = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
 <device>
  <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
  <friendlyName>测试电视 (Mock DLNA)</friendlyName>
  <manufacturer>R-Music</manufacturer>
  <modelName>MockRenderer</modelName>
  <serviceList>
   <service>
    <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
    <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
    <controlURL>/AVTransport/Control</controlURL>
    <eventSubURL>/AVTransport/Event</eventSubURL>
    <SCPDURL>/AVTransport/scpd.xml</SCPDURL>
   </service>
  </serviceList>
 </device>
</root>
"""


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/xml;charset=utf-8"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/desc.xml"):
            return self._send(200, DESC)
        self._send(404, "<notFound/>")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode("utf-8", "ignore")
        action = (self.headers.get("SOAPAction") or "").strip('"').split("#")[-1]
        uri = ""
        m = re.search(r"<CurrentURI>(.*?)</CurrentURI>", raw, re.S)
        if m:
            uri = m.group(1).strip()
        with open(REC, "a") as f:
            f.write(json.dumps({"t": time.time(), "action": action, "uri": uri}) + "\n")
        print("[mock-dlna] 收到 %s %s" % (action, uri[:70]), flush=True)
        self._send(200, '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                        "<s:Body><u:%sResponse xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\"/></s:Body>"
                        "</s:Envelope>" % action)


def ssdp_loop(stop):
    """真的加入 SSDP 组播组并回应 M-SEARCH，这样小桥能发现它"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", 1900))
    mreq = struct.pack("4sl", socket.inet_aton("239.255.255.250"), socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.settimeout(1)
    print("[mock-dlna] SSDP 监听中 (:1900)", flush=True)
    while not stop.is_set():
        try:
            data, addr = s.recvfrom(65507)
        except socket.timeout:
            continue
        except OSError:
            break
        if b"M-SEARCH" not in data:
            continue
        st = ""
        m = re.search(rb"(?im)^ST:\s*(\S+)", data)
        if m:
            st = m.group(1).decode()
        if "MediaRenderer" not in st and "ssdp:all" not in st and "upnp:rootdevice" not in st:
            continue
        resp = ("HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\nEXT:\r\n"
                "LOCATION: http://127.0.0.1:%d/desc.xml\r\nSERVER: Mock/1.0 UPnP/1.0 MockRenderer/1.0\r\n"
                "ST: %s\r\nUSN: uuid:r-music-mock::%s\r\n\r\n" % (PORT, st or "ssdp:all", st or "ssdp:all"))
        try:
            s.sendto(resp.encode(), addr)
        except OSError:
            pass
    s.close()


if __name__ == "__main__":
    if os.path.exists(REC):
        os.unlink(REC)
    stop = threading.Event()
    threading.Thread(target=ssdp_loop, args=(stop,), daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("[mock-dlna] HTTP 服务 http://127.0.0.1:%d/desc.xml" % PORT, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop.set()
