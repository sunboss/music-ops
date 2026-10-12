"""AI 点歌链路自测（用模拟大模型响应，不需要真实密钥）"""
import json
import sys
sys.path.insert(0, "/app")
import server  # noqa: E402

# 1) 解析环节：用模拟的模型回复验证 JSON 解析与字段兜底
cases = [
    ("来首周杰伦的慢歌", {"keywords": ["周杰伦 慢歌", "周杰伦 情歌"], "artist": "周杰伦",
                          "mood": "抒情", "count": 3, "reply": "给你挑了几首周杰伦的慢歌"}),
    ("适合深夜写代码听的", {"keywords": ["纯音乐 专注", "lofi"], "artist": "", "mood": "专注",
                            "count": 5, "reply": "深夜写代码的背景音"}),
]
for text, fake in cases:
    server.AI_API_KEY = "dummy"
    server.ai_chat = lambda *a, **k: json.dumps(fake, ensure_ascii=False)
    plan = server.ai_plan(text)
    print("输入: %r -> 关键词 %s, artist=%r, mood=%r, count=%s" %
          (text, plan["keywords"], plan["artist"], plan["mood"], plan["count"]))

# 2) 字段兜底：模型返回残缺 JSON 时不应崩
server.ai_chat = lambda *a, **k: json.dumps({"reply": "只有回复"})
print("残缺回复兜底 ->", server.ai_plan("随便听听"))

# 3) 检索环节：真实调用官方搜索
server.ai_chat = lambda *a, **k: json.dumps({"keywords": ["周杰伦 晴天"], "count": 3})
plan = server.ai_plan("来首晴天")
songs = server.search_songs(plan["keywords"][0], plan["count"])
print("检索结果:", [(s["name"], s["artist"], s["duration"]) for s in songs[:3]])

# 4) 端到端：解析 + 检索 + 组装响应
server.AI_API_KEY = "dummy"
server.ai_chat = lambda *a, **k: json.dumps(
    {"keywords": ["周杰伦 晴天"], "artist": "周杰伦", "mood": "", "count": 3,
     "reply": "来首晴天"}, ensure_ascii=False)
plan = server.ai_plan("来首晴天")
out = []
for kw in plan["keywords"]:
    out += server.search_songs(kw, plan["count"])
print("端到端: reply=%r 歌曲数=%d 首曲=%s" %
      (plan["reply"], len(out), out[0]["name"] if out else "-"))
print("全部环节未抛异常 ✔")
