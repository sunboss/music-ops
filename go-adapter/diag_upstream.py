import json
import urllib.request
import urllib.error

UA = {"User-Agent": "Mozilla/5.0"}


def raw(url, t=30):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t).read().decode()


print("=== 1. resolve-best 原始响应 ===")
q = "name=%E6%99%B4%E5%A4%A9&artist=%E5%91%A8%E6%9D%B0%E4%BC%A6&duration=269&sources=kuwo"
try:
    print(raw("http://go-adapter:8811/resolve-best?" + q)[:700])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:500])

print()
print("=== 2. jamendo 能否解析 ===")
q2 = "name=Digital+Pirate&artist=KevinBrauer&duration=95&sources=jamendo"
try:
    d = json.loads(raw("http://go-adapter:8811/resolve-best?" + q2))
    u = d.get("url") or ""
    print("status=%s source=%s url=%s" % (d.get("status"), d.get("source"), u[:90]))
    if u.startswith("http"):
        with urllib.request.urlopen(urllib.request.Request(u, headers=dict(UA, Range="bytes=0-0")), timeout=20) as r:
            print("  取Range: 状态=%s CR=%s" % (r.status, r.headers.get("Content-Range")))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:400])

print()
print("=== 3. 服务器能不能直连酷我 anti 接口 ===")
for u in ["http://antiserver.kuwo.cn/anti.s?type=convert_url&rid=228908&format=mp3&response=url",
          "http://search.kuwo.cn/r.s?client=kt&all=%E5%91%A8%E6%9D%B0%E4%BC%A6%20%E6%99%B4%E5%A4%A9&pn=0&rn=2&uid=794764845&ver=12&vipver=1&show_copyright_off=1&newsearch=1&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json"]:
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "okhttp/3.10.0"}), timeout=15) as r:
            body = r.read()[:200].decode(errors="ignore")
            print("  %s -> %s | %s" % (u.split("?")[0], r.status, body.replace("\n", " ")[:150]))
    except Exception as e:
        print("  %s -> 异常 %s" % (u.split("?")[0], str(e)[:100]))
