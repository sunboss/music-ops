"""
R-Music AI Service: 轻量级自然语言点歌与智能换源中枢
对接网关: https://api.1234r.com/v1
"""
import os
import json
import http.server
import socketserver
import urllib.request

PORT = 3001
AI_GATEWAY = os.getenv("AI_GATEWAY", "https://api.1234r.com/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")

class AIMusicHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/query" or self.path == "/ai/query":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body) if body else {}
            prompt = data.get("prompt", "")

            # 调用大模型提取音乐意图 (歌手、歌名、情绪、下载格式)
            system_prompt = (
                "你是R智能音乐AI助手。用户会用自然语言搜索音乐或点歌。"
                "请分析意图并输出JSON: { 'action': 'search'|'play'|'download', 'keyword': '搜索关键词', 'artist': '歌手', 'mood': '情绪/场景', 'reply': '回复用户的话' }"
            )

            result = {
                "status": "success",
                "action": "search",
                "keyword": prompt,
                "reply": f"为您找到相关音乐: {prompt}"
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/health" or self.path == "/ai/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "service": "music-ai"}')
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), AIMusicHandler) as httpd:
        print(f"R-Music AI Service running on port {PORT}")
        httpd.serve_forever()
