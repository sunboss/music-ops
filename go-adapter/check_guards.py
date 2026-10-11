"""验证辅助函数对异常输入的健壮性（整数 id / 空 / None）"""
import sys
sys.path.insert(0, "/app")
import server  # noqa: E402

print("song_detail(整数 4872687) ->", server.song_detail(4872687))
print("official_url(整数 4872687) ->", "无直链(正常)" if server.official_url(4872687)[0] is None else "有直链")
print("song_detail(None) ->", server.song_detail(None))
print("song_detail('') ->", server.song_detail(""))
print("song_detail('  ') ->", server.song_detail("  "))
print("official_url(None) ->", server.official_url(None))
print("全部未抛异常 ✔")
