"""验证适配器自动回退：主地址（国内隧道）不通时，应自动回落到本地容器"""
import sys
sys.path.insert(0, "/app")
import server  # noqa: E402

print("主地址:", server.GO_ADAPTER)
print("备用地址:", server.GO_ADAPTER_FALLBACK)

print("\n1) 正常情况（走国内隧道）")
r = server.go_resolve("晴天", "周杰伦", "叶惠美", 269)
print("   结果:", "✔ 拿到直链" if (r or {}).get("url") else "✘ 无", (r or {}).get("source"))

print("\n2) 模拟隧道挂掉（主地址改成不存在的端口）")
server.GO_ADAPTER = "http://172.19.0.1:59999"
r = server.go_resolve("晴天", "周杰伦", "叶惠美", 269)
print("   结果:", "✔ 自动回退成功，拿到直链" if (r or {}).get("url") else "✘ 回退失败",
      (r or {}).get("source"))

print("\n3) 两个地址都不通")
server.GO_ADAPTER_FALLBACK = "http://172.19.0.1:59998"
r = server.go_resolve("晴天", "周杰伦", "叶惠美", 269)
print("   结果:", r, "（None 即预期：如实报告不可用，不伪造）")
