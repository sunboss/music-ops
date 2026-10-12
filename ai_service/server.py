"""
R-Music Enhancer（Go 换源接入版）
--------------------------------------------------------------------------
职责：
1. /api/song/url       先问 music-api；官方不可用时调用 Go 适配器做“严格匹配”换源
2. /api/audio/proxy    同源音频代理，隐藏第三方带签名的临时直链，透传 Range
3. /api/*              其余接口透明代理到 music-api:3000
4. /health             健康检查

接入原则：
- 只有严格匹配通过（歌名+版本、歌手、专辑、时长）才回填；否则返回官方原结果
  （url=null），前端显示“无可用音源”，绝不播放别的版本。
- size/br 只用实测值：size 取上游 Content-Range 的总长度，br = size*8/时长；
  测不到就填 0，不伪造。
- 灰色歌曲（列表可播放性）逻辑保持原样，不改动。
"""
import os
import re
import json
import time
import sqlite3
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

PORT = int(os.getenv("PORT", "3001"))
# ---------------------------------------------------------------- AI 网关
# 大模型网关（OpenAI 兼容）。密钥只从环境变量读，绝不写进代码或日志。
AI_GATEWAY = os.getenv("AI_GATEWAY", "https://api.1234r.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")


def _load_ai_key():
    """密钥优先取环境变量；否则读挂载文件（不写进代码、不打印、不提交）。
    文件路径：容器内 /data/ai_key.txt（对应服务器 data/ai_key.txt）"""
    v = (os.getenv("AI_API_KEY") or "").strip()
    if v:
        return v
    for f in (os.getenv("AI_API_KEY_FILE", ""), "/data/ai_key.txt"):
        if not f:
            continue
        try:
            with open(f, "r") as fh:
                t = fh.read().strip()
            if t:
                return t
        except Exception:
            pass
    return ""


AI_API_KEY = _load_ai_key()
MUSIC_API_UPSTREAM = os.getenv("MUSIC_API_UPSTREAM", "http://music-api:3000")
GO_ADAPTER = os.getenv("GO_ADAPTER", "http://go-adapter:8811")
# 备用地址：主地址（国内隧道）挂掉时自动回落，避免换源整体失效
GO_ADAPTER_FALLBACK = os.getenv("GO_ADAPTER_FALLBACK", "")
FALLBACK_SOURCES = os.getenv("FALLBACK_SOURCES", "kuwo,jamendo")
DATA_DIR = os.getenv("DATA_DIR", "/data")
CACHE_DB = os.path.join(DATA_DIR, "unblock_cache.db")
CACHE_TTL = 1800          # 上游直链带签名会过期，30 分钟后重新解析
ROOT = ""
AUDIO_DIR = os.path.join(DATA_DIR, "audio_cache")   # 整曲落盘：播放不再依赖会过期的签名直链
AUDIO_EXTS = (".mp3", ".m4a", ".flac", ".aac", ".mp4")
AUDIO_MAX_FILES = 400                                # 超出按最近播放时间淘汰
REJECT_MARK = "__REJECTED__"                          # 上游只有试听片段时的标记，避免反复重试
UA_BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
START_TS = int(time.time())
# 构建标识会随本文件内容变化：客户端据此自动清理旧缓存并重载


def _build_id():
    """本文件内容的短哈希，作为构建标识：内容一变，客户端就能感知并自愈刷新"""
    try:
        import hashlib
        with open(__file__, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return str(START_TS)


BUILD = _build_id()


# ------------------------------------------------------------------ 缓存
def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(CACHE_DB)
    c.execute("CREATE TABLE IF NOT EXISTS url_cache (song_id TEXT PRIMARY KEY, url TEXT, expire REAL)")
    return c


def cache_get(sid):
    """返回 (upstream_url, size, br, source)；未命中返回 None"""
    try:
        c = _db()
        row = c.execute("SELECT url, expire FROM url_cache WHERE song_id=?", (sid,)).fetchone()
        c.close()
        if row and row[1] and time.time() < row[1] and row[0]:
            parts = row[0].split("\t")
            size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            br = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            src = parts[3] if len(parts) > 3 else ""
            return parts[0], size, br, src
    except Exception:
        pass
    return None


def _mark_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(CACHE_DB)
    c.execute("CREATE TABLE IF NOT EXISTS unplayable (song_id TEXT PRIMARY KEY, until REAL)")
    return c


UNPLAYABLE_TTL = 86400 * 3      # 登记 3 天内视为「无完整音源」，到期自动重试


def mark_unplayable(sid):
    """登记为「全网拿不到完整音源」，列表里保持灰色，避免用户反复点到空"""
    try:
        c = _mark_db()
        c.execute("INSERT OR REPLACE INTO unplayable VALUES (?,?)",
                  (str(sid), time.time() + UNPLAYABLE_TTL))
        c.commit()
        c.close()
    except Exception:
        pass


def is_unplayable(sid):
    try:
        c = _mark_db()
        row = c.execute("SELECT until FROM unplayable WHERE song_id=?", (str(sid),)).fetchone()
        c.close()
        return bool(row and row[0] and time.time() < row[0])
    except Exception:
        return False


def cache_del(sid):
    try:
        c = _db()
        c.execute("DELETE FROM url_cache WHERE song_id=?", (sid,))
        c.commit()
        c.close()
    except Exception:
        pass


def cache_set(sid, url, size=0, br=0, source=""):
    try:
        c = _db()
        c.execute("INSERT OR REPLACE INTO url_cache VALUES (?,?,?)",
                  (sid, "%s\t%d\t%d\t%s" % (url, size, br, source), time.time() + CACHE_TTL))
        c.commit()
        c.close()
    except Exception:
        pass


# ------------------------------------------------------------------ 上游
def _open(url, headers=None, timeout=10, data=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}, data=data),
                                  timeout=timeout)


def song_detail(sid):
    """返回 (name, artist, album, duration_seconds)"""
    sid = str(sid or "").strip()     # 防御：调用方可能传整数 id
    if not sid:
        return "", "", "", 0
    try:
        with _open(MUSIC_API_UPSTREAM + "/song/detail?ids=" + sid,
                   {"User-Agent": "R-Music-Enhancer"}, 4) as r:
            d = json.loads(r.read().decode("utf-8"))
        s = (d.get("songs") or [{}])[0]
        artist = " ".join([a.get("name", "") for a in s.get("ar", []) if a.get("name")])
        album = ((s.get("al") or {}).get("name") or "")
        return s.get("name", ""), artist, album, int(s.get("dt", 0) or 0) // 1000
    except Exception as e:
        print("[Enhancer] 取歌曲信息失败 %s: %s" % (sid, e))
        return "", "", "", 0


def measure_size(url, sid=None):
    """用 Range 取真实总字节数；取不到返回 0（不编造）"""
    if sid:
        lp = audio_cached(sid)
        if lp:
            return os.path.getsize(lp)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            cr = r.headers.get("Content-Range") or ""
            r.read(1)
        m = re.search(r"/(\d+)\s*$", cr)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def go_call(path, timeout=60):
    """调用 Go 适配器。主地址（国内隧道）连不上时自动回退到备用地址（本地容器）。
    业务失败（HTTP 404/502 等）不换地址——那是「确实没有」，不是网络问题。"""
    last = None
    for base in [b for b in (GO_ADAPTER, GO_ADAPTER_FALLBACK) if b]:
        try:
            with urllib.request.urlopen(base.rstrip("/") + path, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            last = e
            print("[Enhancer] 适配器地址不可用(%s): %s" % (base, str(e)[:60]))
    raise last if last else RuntimeError("no go adapter configured")


def go_resolve(name, artist, album, dur):
    """调用 Go 适配器做严格匹配换源；无匹配返回 None"""
    q = urllib.parse.urlencode({"name": name, "artist": artist, "album": album,
                                "duration": str(dur or 0), "sources": FALLBACK_SOURCES})
    try:
        return go_call("/resolve-best?" + q, timeout=25)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            if e.code == 404:
                print("[Enhancer] 无可用音源: %s / %s | %s" % (name, artist, body.get("attempts")))
        except Exception:
            pass
        return None
    except Exception as e:
        print("[Enhancer] Go 适配器不可用: %s" % e)
        return None


def ai_enabled():
    return bool(AI_API_KEY.strip())


def ai_chat(messages, timeout=40, temperature=0.3, json_mode=True):
    """调用大模型网关；返回助手回复文本。失败抛出异常（由调用方明确报错）"""
    if not ai_enabled():
        raise RuntimeError("未配置 AI_API_KEY")
    body = {"model": AI_MODEL, "messages": messages, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        AI_GATEWAY.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 # 网关前置了 Cloudflare，缺少浏览器形态的 UA 会被 403 拦掉
                 "User-Agent": UA_BROWSER,
                 "Accept": "application/json",
                 "Authorization": "Bearer " + AI_API_KEY.strip()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return (d.get("choices") or [{}])[0].get("message", {}).get("content", "")


PLAN_PROMPT = (
    "你是音乐检索助手。把用户的中文自然语言需求转成 JSON（只输出 JSON，不要解释）：\n"
    '{"keywords":["用于音乐平台搜索的词",...],"artist":"歌手名，没有则空串",'
    '"mood":"情绪或场景，没有则空串","count":5,"reply":"一句简短中文回复"}\n'
    "要求：keywords 用具体可检索的歌名/歌手/主题词，2-3 个，不要整句话；"
    "count 取 3-10；reply 用用户的语言回答。")


def _strip_fence(s):
    """模型常把 JSON 包在 ```json 代码块里，这里剥掉"""
    t = (s or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


RADIO_PROMPT = (
    "你是音乐电台策划。根据用户描述生成一张歌单的检索计划（只输出 JSON，不要解释）：\n"
    '{"title":"歌单名(10字内)","reply":"一句中文回复",'
    '"keywords":["检索词1","检索词2",...]}\n'
    "要求：keywords 给 6-8 个不同角度但都贴合需求的检索词（歌手名、代表作、风格词、场景词混合），"
    "每个都要具体到能在音乐平台搜到歌，不要整句描述。")


def ai_radio_plan(text):
    """让大模型产出电台检索计划（多关键词，用于凑出一整张歌单）"""
    out = ai_chat([{"role": "system", "content": RADIO_PROMPT},
                   {"role": "user", "content": text}], temperature=0.6)
    plan = json.loads(_strip_fence(out))
    kws = [str(k) for k in (plan.get("keywords") or []) if str(k).strip()]
    if not kws:
        kws = [text]
    plan["keywords"] = kws[:8]
    return plan


def ai_plan(text):
    """让大模型把自然语言变成结构化检索条件"""
    out = ai_chat([{"role": "system", "content": PLAN_PROMPT},
                   {"role": "user", "content": text}])
    plan = json.loads(_strip_fence(out))
    if not isinstance(plan.get("keywords"), list) or not plan["keywords"]:
        plan["keywords"] = [text]
    plan["keywords"] = [str(k) for k in plan["keywords"]][:3]
    try:
        plan["count"] = max(1, min(10, int(plan.get("count") or 5)))
    except Exception:
        plan["count"] = 5
    return plan


def search_songs(keyword, limit=5):
    """走官方搜索接口取歌（与站点搜索同一数据源）"""
    try:
        with _open(MUSIC_API_UPSTREAM + "/cloudsearch?keywords=" +
                   urllib.parse.quote(keyword) + "&type=1&limit=%d" % limit,
                   {"User-Agent": "R-Music-Enhancer"}, 12) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[Enhancer] AI 搜索失败 %s: %s" % (keyword, e))
        return []
    out = []
    for s in ((d.get("result") or {}).get("songs") or []):
        al = s.get("al") or {}
        out.append({"id": s.get("id"), "name": s.get("name"),
                    "artist": " / ".join(a.get("name", "") for a in (s.get("ar") or [])),
                    "album": al.get("name") or "",
                    "duration": round((s.get("dt") or 0) / 1000.0, 1)})
    return out


def probe_cache_get(sid):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("CREATE TABLE IF NOT EXISTS probeable (song_id TEXT PRIMARY KEY, ok INT, until REAL)")
        row = c.execute("SELECT ok, until FROM probeable WHERE song_id=?", (str(sid),)).fetchone()
        c.close()
        if row and row[1] and time.time() < row[1]:
            return bool(row[0])
    except Exception:
        pass
    return None


def probe_cache_set(sid, ok):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("CREATE TABLE IF NOT EXISTS probeable (song_id TEXT PRIMARY KEY, ok INT, until REAL)")
        c.execute("INSERT OR REPLACE INTO probeable VALUES (?,?,?)",
                  (str(sid), 1 if ok else 0, time.time() + 21600))
        c.commit()
        c.close()
    except Exception:
        pass


def quick_playable(sid):
    """快速判断这首歌有没有「完整音源」，不下载整曲：
    命中落盘缓存最准；否则看官方/换源直链的实际体积是否撑得起这首歌的时长。"""
    sid = str(sid or "").strip()
    if not sid:
        return False
    if audio_cached(sid):
        probe_cache_set(sid, True)
        return True
    cached = probe_cache_get(sid)
    if cached is not None:
        return cached
    ok = _quick_playable_uncached(sid)
    probe_cache_set(sid, ok)
    return ok


def _quick_playable_uncached(sid):
    hit = cache_get(sid)
    if hit:
        return hit[0] != REJECT_MARK and bool(hit[0])
    name, artist, album, dur = song_detail(sid)
    for cand in (official_url(sid)[0], None):
        if cand:
            sz = measure_size(cand)
            if dur and sz >= dur * MIN_BYTES_PER_SEC:
                return True
            break
    if not name:
        return False
    res = go_resolve(name, artist, album, dur)
    u = (res or {}).get("url")
    if not is_http(u):
        return False
    sz = measure_size(u)
    if dur and sz >= dur * MIN_BYTES_PER_SEC:
        return True
    return False


# 翻唱/劣质变体特征词：仅用于降权排序，不做过滤（有正当歌曲含这些词）
BAD_NAME_HINTS = ("翻唱", "cover", "伴奏", "remix", "dj版", "dj弹鼓", "深情版", "片段",
                  "串烧", "铃声", "加速版", "减速版", "slowed", "sped up", "纯音乐版",
                  "钢琴版", "吉他版", "口琴版", "教学", "跟唱")


def bad_variant(name):
    n = (name or "").lower()
    return any(h in n for h in BAD_NAME_HINTS)


def reorder_search_songs(songs):
    """搜索列表降权：把翻唱/伴奏/片段等变体排到后面，原版优先。
    稳定排序，不改变同名同类之间的原有相对顺序。"""
    if not isinstance(songs, list) or len(songs) < 2:
        return songs
    try:
        return sorted(songs, key=lambda s: 1 if bad_variant((s or {}).get("name")) else 0)
    except Exception:
        return songs


# 版本标记：候选歌名里出现「目标没有的」这些词，说明是另一个版本（现场/伴奏/翻唱…），一律不接受
VERSION_MARKERS = ("live", "现场", "演唱会", "remix", "混音", "伴奏", "instrumental", "翻唱",
                   "cover", "纯音乐", "钢琴", "吉他", "口琴", "片段", "串烧", "试听", "铃声",
                   "童声", "女声版", "男声版", "深情版", "加速版", "减速版", "dj版", "教学",
                   "跟唱", "和声", "清唱", "demo", "重制", "新版", "改编")

AI_PICK_PROMPT = (
    "判断下面两条音乐元数据是否指**同一首歌的同一个演唱版本**。\n"
    "只有歌名在标点、繁简、空格、括号等写法上有差异、且歌手一致时才算同一首；\n"
    "如果是翻唱、现场版、重制版、伴奏、混音等不同版本，或歌手不是同一人，就不算。\n"
    '只输出 JSON：{"same":true/false,"reason":"简短中文理由"}\n\n'
    "目标：歌名=%s 歌手=%s 专辑=%s 时长=%s秒\n"
    "候选：歌名=%s 歌手=%s 专辑=%s 时长=%s秒")


def _markers(s):
    t = (s or "").lower()
    return {m for m in VERSION_MARKERS if m in t}


def _norm_loose(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (s or "").lower())


VARIANT_PROMPT = (
    "你在帮音乐换源做检索。下面这首歌在平台上按原元数据搜不到，请给出**同一首歌**的"
    "其它检索写法（只输出 JSON，不要解释）：\n"
    '{"variants":[{"name":"歌名写法","artist":"歌手写法","why":"为什么这么搜"}]}\n'
    "允许的改写：去掉括号里的补充说明只留主标题、补上/修正歌手名（含常见别名、繁简写法、"
    "英文名/中文名互换）、去掉多余副标题。\n"
    "**不允许**换成另一首歌、不允许给出翻唱/现场/伴奏版本。最多 5 条。\n\n"
    "原元数据：歌名=%s 歌手=%s 专辑=%s 时长=%s秒")


def ai_search_variants(name, artist, album, dur):
    """让模型给出同一首歌的其它检索写法（歌名带括号补充、歌手写法怪时最有用）"""
    try:
        out = ai_chat([{"role": "user", "content": VARIANT_PROMPT % (
            name, artist, album or "", dur or "?")}], temperature=0.3)
        v = json.loads(_strip_fence(out))
    except Exception as e:
        print("[Enhancer] AI 检索变体生成失败: %s" % str(e)[:80])
        return []
    out_v = []
    for it in (v.get("variants") or [])[:5]:
        if not isinstance(it, dict):
            continue
        n = str(it.get("name") or "").strip()
        a = str(it.get("artist") or artist or "").strip()
        if n:
            out_v.append({"name": n, "artist": a, "why": str(it.get("why") or "")[:40]})
    return out_v


def _title_compatible(orig, cand):
    """候选歌名必须与原歌名互为包含关系（容忍只有括号补充的差异），防止换到另一首歌"""
    a, b = _norm_loose(orig), _norm_loose(cand)
    if not a or not b:
        return False
    return a in b or b in a


def _judge_same(name, artist, album, dur, cname, cartist, calbum, cdur):
    """让模型对最终候选做一次严格判定：是否为同一首录音"""
    try:
        out = ai_chat([{"role": "user", "content": AI_PICK_PROMPT % (
            name, artist, album or "", dur or "?", cname, cartist, calbum or "", cdur or "?")}],
            temperature=0)
        v = json.loads(_strip_fence(out))
    except Exception as e:
        print("[Enhancer] AI 选源判定失败: %s" % str(e)[:80])
        return None
    return v if v.get("same") else None


ARBITER_PROMPT = (
    "你在给音乐换源做**终审**。规则匹配（歌名严格相等+歌手兼容+时长±8秒）已经失败，"
    "现在把各平台的原始候选交给你判断。\n"
    "挑出与目标是**同一首歌、同一个演唱版本**的候选；\n"
    "· 只有歌名在标点/繁简/空格/括号补充上不同、或歌手名是同一人的不同写法（含英文名、"
    "组合成员写法、`feat.` 差异）时，才算同一首；\n"
    "· 翻唱、Live/现场、重制、伴奏、Remix、加速减速、DJ、童声/女声改编版一律**不算**；\n"
    "· 时长差超过 30 秒基本可判定不是同一录音（除非候选是片段）；\n"
    "· 都不符合就返回 -1，宁可不要也不能选错。\n"
    '只输出 JSON：{"index": 编号或-1, "same": true/false, "reason": "简短中文理由"}\n\n'
    "目标：歌名=%s 歌手=%s 专辑=%s 时长=%s秒\n"
    "候选：\n%s")


def ai_arbitrate(name, artist, album, dur, cands):
    """把各平台候选交给大模型终审，返回选中的候选（dict）或 None"""
    if not cands:
        return None
    lines = []
    for i, c in enumerate(cands):
        lines.append("  [%d] 歌名=%s | 歌手=%s | 专辑=%s | 时长=%s秒 | 平台=%s"
                     % (i, (c.get("name") or "")[:40], (c.get("artist") or "")[:40],
                        (c.get("album") or "")[:24], c.get("duration") or "?",
                        c.get("_source") or "?"))
    try:
        out = ai_chat([{"role": "user", "content": ARBITER_PROMPT % (
            name, artist, album or "", dur or "?", "\n".join(lines))}], temperature=0)
        v = json.loads(_strip_fence(out))
    except Exception as e:
        print("[Enhancer] AI 终审调用失败: %s" % str(e)[:80])
        return None
    if not v.get("same"):
        print("[Enhancer] AI 终审判定不是同一录音: %s" % str(v.get("reason"))[:60])
        return None
    try:
        i = int(v.get("index"))
    except Exception:
        return None
    if i < 0 or i >= len(cands):
        return None
    c = dict(cands[i])
    c["_reason"] = str(v.get("reason") or "")[:60]
    print("[Enhancer] AI 终审选定 [%d] %s / %s / %s秒 (%s) ← %s"
          % (i, c.get("name"), c.get("artist"), c.get("duration"),
             c.get("_source"), c.get("_reason")))
    return c


def gather_candidates(queries, dur):
    """对每个检索写法，向所有来源要原始候选（不要求匹配），合并去重"""
    sources = ",".join([s.strip() for s in FALLBACK_SOURCES.split(",") if s.strip()])
    out, seen = [], set()
    for q in queries[:4]:
        try:
            prm = urllib.parse.urlencode({"name": q["name"], "artist": q["artist"],
                                          "album": "", "duration": int(dur or 0),
                                          "sources": sources})
            r = go_call("/resolve?" + prm, timeout=120)
        except Exception as e:
            print("[Enhancer] 取候选失败(%s): %s" % (q.get("name"), str(e)[:60]))
            continue
        for o in (r.get("outcomes") or []):
            for c in (o.get("candidates") or []):
                if not isinstance(c, dict):
                    continue
                k = ((c.get("name") or "").lower(), (c.get("artist") or "").lower())
                if k in seen:
                    continue
                seen.add(k)
                c = dict(c)
                c["_source"] = o.get("source")
                c["_query"] = q.get("name", "") + " " + q.get("artist", "")
                out.append(c)
    return out


def ai_pick_source(name, artist, album, dur):
    """规则匹配（歌名相等+歌手兼容+时长±8秒）失败时，让大模型在各平台**原始候选**里终审，
    找回同一首录音。返回 {"url","source","song","reason"} 或 None。
    这正是规则的短板：别名/繁简/括号补充/组合成员写法，以及识别翻唱与 Live 版。"""
    if not ai_enabled() or not name:
        return None
    queries = [{"name": name, "artist": artist, "why": "原写法"}]
    queries += ai_search_variants(name, artist, album, dur)

    cands = gather_candidates(queries, dur)[:24]
    if not cands:
        print("[Enhancer] AI 选源：各平台都没有候选 %s / %s" % (name, artist))
        return None
    pick = ai_arbitrate(name, artist, album, dur, cands)
    if not pick:
        return None

    cn, ca = (pick.get("name") or "").strip(), (pick.get("artist") or "").strip()
    cd = pick.get("duration") or 0
    if not cn or not ca:
        return None
    # 硬保险：即便模型说「是」，这两条仍然兜住（模型判断失误时不会污染曲库）
    if dur and cd and abs(cd - dur) > 35:
        print("[Enhancer] AI 选源被时长保险拦下: 候补 %s 秒 vs 目标 %s 秒" % (cd, dur))
        return None
    if _markers(cn) - _markers(name):
        print("[Enhancer] AI 选源被版本标记保险拦下: %s" % cn)
        return None

    # 用终审选定的候选名/歌手去取直链（宽松匹配，不受规则时长约束）
    order = [(pick.get("_source") or "").strip()]
    order += [s.strip() for s in FALLBACK_SOURCES.split(",") if s.strip()]
    for src in order:
        if not src:
            continue
        try:
            prm = urllib.parse.urlencode({"name": cn, "artist": ca, "album": "",
                                          "duration": int(cd or dur or 0), "source": src,
                                          "loose": "1"})
            r = go_call("/resolve-url?" + prm, timeout=90)
        except Exception:
            continue
        u = r.get("url")
        if is_http(u):
            s = r.get("song") or {}
            print("[Enhancer] AI 选源拿到直链 %s / %s ← 平台 %s（%s）"
                  % (s.get("name"), s.get("artist"), src, pick.get("_reason")))
            return {"url": u, "source": src, "song": s,
                    "reason": pick.get("_reason") or "", "query": cn + " " + ca}
    print("[Enhancer] AI 选源选定候选但取链失败: %s / %s" % (cn, ca))
    return None


CURATE_PROMPT = (
    "你是音乐电台主编。下面是为用户需求检索到的**真实可播放**歌曲列表（已确认能完整播放）。\n"
    "请做三件事：①只保留真正贴合需求的歌，并按播放顺序排好（明显不搭、重复、风格跳脱的剔除）；"
    "②给这张歌单起个名字；③用一句话说明编排思路。\n"
    "注意：宁少勿滥，但至少保留 5 首。\n"
    '只输出 JSON：{"title":"歌单名(12字内)","reply":"一句话说明","pick":[编号,编号,...],'
    '"drop":"剔除原因(没有就留空)"}\n'
    "pick 里只放编号，按你希望的播放顺序排列。\n\n"
    "用户需求：%s\n候选歌曲：\n%s")


def ai_curate(text, songs):
    """让大模型对真实可播歌单做取舍与排序（规则做不到的「像不像这个场景」判断）。
    返回 {"title","reply","songs"} 或 None（失败时保留原样）"""
    if not ai_enabled() or len(songs) < 5:
        return None
    lines = []
    for i, s in enumerate(songs):
        lines.append("  [%d] %s / %s / %s秒" % (i, (s.get("name") or "")[:40],
                                                (s.get("artist") or "")[:32],
                                                int(s.get("duration") or 0)))
    try:
        out = ai_chat([{"role": "user", "content": CURATE_PROMPT % (text, "\n".join(lines))}],
                      temperature=0.4)
        v = json.loads(_strip_fence(out))
    except Exception as e:
        print("[Enhancer] AI 策展失败(保留原歌单): %s" % str(e)[:80])
        return None
    pick, seen = [], set()
    for x in (v.get("pick") or []):
        try:
            i = int(x)
        except Exception:
            continue
        if 0 <= i < len(songs) and i not in seen:
            seen.add(i)
            pick.append(i)
    if len(pick) < 5:
        print("[Enhancer] AI 策展结果太少(%d 首)，保留原歌单" % len(pick))
        return None
    ordered = [songs[i] for i in pick]
    rest = [s for i, s in enumerate(songs) if i not in seen]
    print("[Enhancer] AI 策展: 保留 %d 首 / 候选 %d 首，剔除 %d 首 %s"
          % (len(pick), len(songs), len(rest), ("（%s）" % v.get("drop")) if v.get("drop") else ""))
    return {"title": str(v.get("title") or "")[:20], "reply": str(v.get("reply") or "")[:80],
            "songs": ordered + rest, "picked": len(pick)}


def rank_songs(songs, plan):
    """按「与需求的吻合度」排序：指定歌手命中优先，其次歌名关键词命中，最后时长较长者"""
    artist = (plan.get("artist") or "").strip().lower()
    kws = [k.strip().lower() for k in (plan.get("keywords") or []) if k.strip()]

    def score(s):
        sc = 0
        if artist and artist in (s.get("artist") or "").lower():
            sc -= 100                       # 命中指定歌手，最优先
        nm = (s.get("name") or "").lower()
        for k in kws:
            for w in k.split():
                if len(w) >= 2 and w in nm:
                    sc -= 5
                    break
        if bad_variant(nm):
            sc += 30                        # 翻唱/伴奏/片段等变体降权
        return sc

    return sorted(songs, key=score)


def is_http(u):
    """上游取不到真实直链时会返回空串或字符串 "None"，必须挡住，不能当链接回填"""
    return isinstance(u, str) and (u.startswith("http://") or u.startswith("https://"))


def official_url(sid):
    """取官方直链；试听片段（freeTrialInfo 非空）不算可用，返回 None"""
    sid = str(sid or "").strip()     # 防御：调用方可能传整数 id
    if not sid:
        return None, 0
    try:
        with _open(MUSIC_API_UPSTREAM + "/song/url?id=" + urllib.parse.quote(sid) + "&br=320000",
                   {"User-Agent": "R-Music-Enhancer"}, 10) as r:
            d = json.loads(r.read().decode("utf-8"))
        it = (d.get("data") or [{}])[0]
        if it.get("url") and not is_trial_item(it):
            return fix_url(it["url"]), int(it.get("size") or 0)
    except Exception as e:
        print("[Enhancer] 取官方直链失败 %s: %s" % (sid, e))
    return None, 0


def build_entry(sid, up_url, dur, source="fallback", size=None):
    """生成标准网易云 song/url 条目。
    注意：无论官方还是换源，播放地址一律给本服务的代理地址——
    只有经过本服务下载并校验真实时长，才能确认不是 30 秒试听片段。"""
    if size is None:
        size = measure_size(up_url, sid)
    br = int(size * 8 / dur) if (size and dur) else 0
    cache_set(sid, up_url, size, br, source)
    return {"id": int(sid) if sid.isdigit() else 0,
            "url": ROOT + "/api/audio/proxy?id=" + urllib.parse.quote(sid),
            "br": br, "size": size, "md5": None, "code": 200, "type": "mp3",
            "freeTrialInfo": None, "level": None, "source": source, "expi": CACHE_TTL}


# ------------------------------------------------- 试听片段拦截（否则只能听 30 秒）
def is_trial_item(it):
    """官方对 VIP 曲会返回 30 秒试听片段，freeTrialInfo 非空即为试听"""
    if not isinstance(it, dict):
        return False
    if it.get("freeTrialInfo"):
        return True
    return False


def strip_trial(data):
    """把试听片段从回填数据里去掉：宁可显示“无可用音源”，也不给 30 秒试听"""
    try:
        for it in (data or {}).get("data") or []:
            if isinstance(it, dict) and is_trial_item(it):
                print("[Enhancer] 拦截到官方试听片段 id=%s，改为无音源" % it.get("id"))
                it["url"] = None
                it["code"] = 404
                it["freeTrialInfo"] = None
    except Exception:
        pass
    return data


# ------------------------------------------------- 音频真实时长校验
SR_TAB = {0: 44100, 1: 48000, 2: 32000}
BR_TAB = {1: [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
          3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]}


def probe_duration(path):
    """读取音频文件真实时长（秒）；解析不出返回 0。用于挡住上游给的试听/占位片段。"""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
            if head[:4] == b"fLaC":
                # FLAC: STREAMINFO 里有采样率与总采样数
                f.seek(0)
                d = f.read(64)
                b = int.from_bytes(d[18:26], "big")
                sr = b >> 44
                total = b & ((1 << 36) - 1)
                return (total / float(sr)) if sr and total else 0.0
            if head[4:8] == b"ftyp":
                f.seek(0)
                data = f.read(4 * 1024 * 1024)
                i = data.find(b"mvhd")
                if i < 0:
                    return 0.0
                if data[i + 4] == 1:
                    ts = int.from_bytes(data[i + 24:i + 28], "big")
                    du = int.from_bytes(data[i + 28:i + 36], "big")
                else:
                    ts = int.from_bytes(data[i + 16:i + 20], "big")
                    du = int.from_bytes(data[i + 20:i + 24], "big")
                return du / float(ts) if ts else 0.0
            f.seek(0)
            data = f.read()
    except Exception:
        return 0.0

    i = 0
    if data[:3] == b"ID3" and len(data) > 10:
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        i = 10 + size
    total, n = 0.0, 0
    n = 0
    size = len(data)
    while i < size - 4 and n < 200000:
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            ver = (data[i + 1] >> 3) & 0x03
            layer = (data[i + 1] >> 1) & 0x03
            bri = (data[i + 2] >> 4) & 0x0F
            sri = (data[i + 2] >> 2) & 0x03
            pad = (data[i + 2] >> 1) & 0x01
            if ver in (2, 3) and layer == 1 and 0 < bri < 15 and sri != 3:
                sr = SR_TAB[sri] * (2 if ver == 2 else 1)
                br = BR_TAB[3 if ver == 3 else 1][bri] * 1000
                spf = 1152 if ver == 3 else 576
                flen = int(spf // 8 * br / sr) + pad
                if flen <= 0:
                    break
                total += spf / float(sr)
                n += 1
                i += flen
                continue
        i += 1
    return total


# 低于这个码率（字节/秒）在音乐里不现实，用于在解析不出时长时兜底判断
MIN_BYTES_PER_SEC = 6000.0          # 约 48 kbps
# 网易云「外链播放」地址：前端在取不到源时会拿它兜底，但它对 VIP 曲只返回 30 秒试听。
# 我们把它也纳入候选，但必须经过体积/时长校验才采纳。
NETEASE_OUTER = "https://music.163.com/song/media/outer/url?id="


def duration_ok(path, expected):
    """文件必须是完整音频。两道判断：
    1) 能解析出真实时长 -> 必须与歌曲时长吻合
    2) 解析不出（少见格式）-> 用体积下限兜底，挡住 30 秒片段冒充长曲
    """
    actual = probe_duration(path)
    if not expected:
        return True, actual
    try:
        size = os.path.getsize(path)
    except Exception:
        size = 0
    if actual > 0:
        # 交叉校验：出现下列任一情况，说明时长解析不可信（多半是少见容器格式），
        # 改用体积兜底 —— 避免误伤正常音频，同时仍能挡住试听片段
        #   ① 时长与体积矛盾（暗含码率低于 2.4kbps）
        #   ② 解析出的时长极短但文件很大（真片段不会又长又大）
        unreliable = bool(size) and ((size / actual < 300) or (actual < 5 and size > 1000000))
        if unreliable:
            print("[Enhancer] 时长(%0.1fs)与体积(%d 字节)不匹配，解析不可信，改用体积兜底"
                  % (actual, size))
            actual = 0.0
        else:
            return actual >= expected - 8, actual
    if not size:
        return True, actual
    if expected > 20 and size < expected * MIN_BYTES_PER_SEC:
        print("[Enhancer] 时长无法解析且体积过小(%d 字节 / 期望 %d 秒)，判为片段" % (size, expected))
        return False, actual
    return True, actual


# ------------------------------------------------- 整曲落盘（解决播放中途直链过期）
def audio_cached(sid):
    """已完整落盘则返回本地路径"""
    for e in AUDIO_EXTS:
        f = os.path.join(AUDIO_DIR, sid + e)
        if os.path.exists(f) and os.path.getsize(f) > 4096:
            return f
    return None


def audio_ext(ctype, url):
    c = (ctype or "").lower()
    if "mp4" in c or "m4a" in c or "aac" in c:
        return ".m4a"
    if "flac" in c:
        return ".flac"
    u = (url or "").lower().split("?")[0]
    for e in AUDIO_EXTS:
        if u.endswith(e):
            return e
    return ".mp3"


def evict_audio():
    """按最近使用时间保留最近 AUDIO_MAX_FILES 首，避免磁盘无限增长"""
    try:
        fs = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR) if f.endswith(AUDIO_EXTS)]
        if len(fs) <= AUDIO_MAX_FILES:
            return
        fs.sort(key=os.path.getmtime)
        for f in fs[:len(fs) - AUDIO_MAX_FILES]:
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception:
        pass


def fetch_to_disk(sid, up_url, expected=0, timeout=90):
    """整首音频落盘。签名直链时效很短，落盘后播放与拖动都不再依赖它。"""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    tmp = os.path.join(AUDIO_DIR, sid + ".part")
    try:
        req = urllib.request.Request(up_url, headers={"User-Agent": UA_BROWSER})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ext = audio_ext(r.headers.get("Content-Type"), up_url)
            n = 0
            with open(tmp, "wb") as f:
                while True:
                    c = r.read(262144)
                    if not c:
                        break
                    f.write(c)
                    n += len(c)
        if n < 10240:
            os.remove(tmp)
            print("[Enhancer] 落盘内容过小(%d 字节)，丢弃 %s" % (n, sid))
            return None, "too_small"
        final = os.path.join(AUDIO_DIR, sid + ext)
        os.replace(tmp, final)
        ok, actual = duration_ok(final, expected)
        if not ok:
            try:
                os.remove(final)
            except Exception:
                pass
            print("[Enhancer] 时长不符被拒：%s 期望 %.0f 秒，实际只有 %.1f 秒（试听片段或占位音频）"
                  % (sid, expected or 0, actual))
            return None, "duration_rejected"
        print("[Enhancer] 整曲落盘 %s (%d 字节 %s, 实测 %.1f 秒)" % (sid, n, ext, actual))
        evict_audio()
        return final, "ok"
    except Exception as e:
        print("[Enhancer] 落盘失败 %s: %s" % (sid, e))
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return None, "fetch_error"


# ------------------------------------------------- 灰色歌曲处理（保持原样）
def clean_song_title(title):
    if not title:
        return ""
    return re.sub(r"\(.*?\)|\[.*?\]|【.*?】|（.*?）", "", title).strip()


def ungrey_song(s):
    if not isinstance(s, dict):
        return
    # 已知拿不到完整音源的曲目：保持灰色，让列表如实反映「不能播」
    try:
        if s.get("id") and is_unplayable(s.get("id")):
            return
    except Exception:
        pass
    if s.get("fee") in (1, 4, 8):
        s["fee"] = 0
    if s.get("noCopyrightRcmd"):
        s["noCopyrightRcmd"] = None
    p = s.get("privilege")
    if not isinstance(p, dict):
        p = {}
        s["privilege"] = p
    if p.get("st") in (-100, -200):
        p["st"] = 0
    if p.get("fee") in (1, 4, 8):
        p["fee"] = 0
    p["plLevel"] = "exhigh"
    p["dlLevel"] = "exhigh"
    if not p.get("pl"):
        p["pl"] = 320000
    if not p.get("dl"):
        p["dl"] = 320000
    if not p.get("fl"):
        p["fl"] = 320000


def ungrey_walk(o):
    if isinstance(o, dict):
        if "privilege" in o or "fee" in o or "noCopyrightRcmd" in o:
            ungrey_song(o)
        for v in o.values():
            if isinstance(v, (dict, list)):
                ungrey_walk(v)
    elif isinstance(o, list):
        for v in o:
            if isinstance(v, (dict, list)):
                ungrey_walk(v)


def fix_url(u):
    if u and u.startswith("http://"):
        return "https://" + u[7:]
    return u


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization,Cookie,Range")

    def _json(self, code, data):
        b = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _up(self, path, query):
        # 网易云 /search 接口返回的数据结构已损坏（歌名/歌手全部错乱），
        # /cloudsearch 才是正确的搜索接口，且字段与前端一致（ar/al/dt/fee/privilege）
        if path == "/search":
            path = "/cloudsearch"
        url = MUSIC_API_UPSTREAM + path + (("?" + query) if query else "")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": self.headers.get("User-Agent", "R-Music"),
                "Cookie": self.headers.get("Cookie", "")})
            if self.command == "POST":
                ln = int(self.headers.get("Content-Length", 0) or 0)
                req.data = self.rfile.read(ln) if ln else None
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            return 502, json.dumps({"code": 502, "msg": str(e)}).encode("utf-8")

    # ------------------------------------------------------------ song/url
    def handle_song_url(self, query):
        prm = urllib.parse.parse_qs(query or "")
        sid = (prm.get("id", [""])[0].split(",")[0] or "").strip()
        print("[Enhancer] 取源请求 id=%s UA=%s" % (sid, (self.headers.get("User-Agent") or "")[:40]))

        if sid:
            hit = cache_get(sid)
            if hit and hit[0] == REJECT_MARK:
                # 各来源都只有试听片段：仍然返回我们自己的地址（播放时会明确失败），
                # 绝不返回 null —— 否则播放器会回落到网易云外链，只能听 30 秒
                mark_unplayable(sid)
                return self._json(200, {"code": 200, "data": [self._item(sid, 0, 0, "no-source")]})
            if hit:
                _, size, br, src = hit
                return self._json(200, {"code": 200, "data": [self._item(sid, size, br, src)]})

        # 问官方：只用于判断「有没有音源」和取 size/br。
        # 播放地址一律走本服务的代理——官方直链可能是 30 秒试听，直接交给播放器会只播 30 秒。
        code, body = self._up("/song/url", query)
        data = None
        off_url = None
        try:
            data = json.loads(body.decode("utf-8"))
            it = (data.get("data") or [{}])[0]
            if it.get("url") and not it.get("freeTrialInfo"):
                off_url = fix_url(it["url"])
        except Exception:
            data = None

        if not sid:
            return self._json(200, strip_trial(data) or {"code": 404, "data": []})

        name, artist, album, dur = song_detail(sid)
        if not name:
            return self._json(200, strip_trial(data) or {"code": 404, "data": []})
        dur = dur or 0

        if off_url:
            try:
                entry = build_entry(sid, off_url, dur, "official")
                print("[Enhancer] 官方可用(经代理校验播放) %s / %s (%d 字节)"
                      % (name, artist, entry["size"]))
                return self._json(200, {"code": 200, "data": [entry]})
            except Exception as e:
                print("[Enhancer] 官方条目构造失败: %s" % e)

        # 官方不可用 → 严格匹配换源
        res = go_resolve(name, artist, album, dur)
        if not res or not is_http(res.get("url")):
            # 最后试网易云外链：体积够长才采纳（VIP 曲它只给 30 秒）
            osz = measure_size(NETEASE_OUTER + urllib.parse.quote(sid))
            if dur and osz >= dur * MIN_BYTES_PER_SEC:
                entry = build_entry(sid, NETEASE_OUTER + urllib.parse.quote(sid), dur,
                                    "netease-outer", size=osz)
                print("[Enhancer] 外链可用且体积达标 %s / %s (%d 字节)" % (name, artist, osz))
                return self._json(200, {"code": 200, "data": [entry]})
            print("[Enhancer] 未换到完整音源: %s / %s (原因: %s, 外链 %d 字节判为片段) "
                  "→ 登记为无音源，列表保持灰色"
                  % (name, artist, (res or {}).get("attempts"), osz))
            mark_unplayable(sid)
            return self._json(200, {"code": 200, "data": [self._item(sid, 0, 0, "no-source")]})
        try:
            entry = build_entry(sid, res["url"], dur, "fallback")
            print("[Enhancer] 换源命中 %s / %s ← %s (%d 字节)" %
                  (name, artist, res.get("source"), entry["size"]))
            return self._json(200, {"code": 200, "data": [entry]})
        except Exception as e:
            print("[Enhancer] 回填失败: %s" % e)
            return self._json(200, strip_trial(data) or {"code": 404, "data": []})

    def _item(self, sid, size, br, source):
        return {"id": int(sid) if sid.isdigit() else 0,
                "url": ROOT + "/api/audio/proxy?id=" + urllib.parse.quote(sid),
                "br": br, "size": size, "md5": None, "code": 200, "type": "mp3",
                "freeTrialInfo": None, "level": None, "source": source or "fallback",
                "expi": CACHE_TTL}

    def _ai_collect(self, keywords, want, per_kw=8, limit=20):
        """按关键词批量取候选 -> 重排 -> 并发探活，返回（可播列表, 全部候选）"""
        cand, seen = [], set()
        for kw in keywords:
            for s in search_songs(kw, per_kw):
                if s.get("id") and s["id"] not in seen:
                    seen.add(s["id"])
                    cand.append(s)
        cand = rank_songs(cand, {"artist": want.get("artist", ""), "keywords": keywords})
        import concurrent.futures as cf
        pool = cand[:72]
        playable, keys = [], set()
        t0 = time.time()
        ex = cf.ThreadPoolExecutor(max_workers=16)
        try:
            futs = {ex.submit(quick_playable, s["id"]): s for s in pool}
            for f in cf.as_completed(futs):
                s = futs[f]
                try:
                    ok = f.result()
                except Exception:
                    ok = False
                s["playable"] = bool(ok)
                k = ((s.get("name") or "").lower().strip(), (s.get("artist") or "").lower().strip())
                if ok and k not in keys:          # 同名同歌手只保留一首
                    keys.add(k)
                    playable.append(s)
                    if len(playable) >= limit:
                        break
                if time.time() - t0 > 30 and len(playable) >= 5:
                    print("[Enhancer] 探活超 30 秒，先交付已确认的 %d 首" % len(playable))
                    break                          # 时间预算：不让用户等太久
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        return playable[:limit], cand

    # ------------------------------------------------------------ AI 电台/歌单
    def handle_ai_radio(self, text, want=18):
        """一句话生成整张歌单：多关键词检索 + 探活，只交付能完整播放的"""
        try:
            plan = ai_radio_plan(text)
        except Exception as e:
            print("[Enhancer] AI 电台解析失败: %s" % e)
            return self._json(502, {"error": "AI 解析失败: %s" % str(e)[:160]})
        songs, _ = self._ai_collect(plan["keywords"], plan, per_kw=8, limit=want)
        if len(songs) < min(8, want):
            # 不够就再要一轮关键词（最多补一次，避免无限循环）
            try:
                more = ai_radio_plan(text + "（再给 6 个不同的检索词，避免与上面重复）")
                extra, _ = self._ai_collect(more["keywords"], plan, per_kw=8,
                                            limit=want - len(songs))
                have = {s["id"] for s in songs}
                songs += [s for s in extra if s["id"] not in have]
            except Exception as e:
                print("[Enhancer] AI 电台补词失败: %s" % e)
        title = plan.get("title") or "AI 电台"
        reply = plan.get("reply") or ""
        # 让大模型对真实可播歌单做策展（取舍 + 排序 + 命名）
        cur = ai_curate(text, songs)
        if cur:
            title = cur["title"] or title
            reply = cur["reply"] or reply
            songs = cur["songs"]
        songs = songs[:want]
        print("[Enhancer] AI 电台 %r -> %d 首可播（关键词 %d 个，策展=%s）"
              % (text[:24], len(songs), len(plan["keywords"]), bool(cur)))
        return self._json(200, {"title": title, "reply": reply,
                                "curated": bool(cur), "picked": (cur or {}).get("picked"),
                                "plan": {"keywords": plan["keywords"]},
                                "songs": songs, "playable_count": len(songs)})

    # ------------------------------------------------------------ AI 点歌
    def handle_ai_query(self, query, body=None):
        """自然语言点歌：大模型把一句话变成检索条件 -> 官方搜索 -> 返回可点播的歌曲列表"""
        text = ""
        want = 0
        if body:
            try:
                b = json.loads(body.decode("utf-8", "ignore")) or {}
                text = b.get("q", "")
                if b.get("mode") == "radio":
                    want = int(b.get("count") or 18)
            except Exception:
                text = ""
        if not text:
            prm = urllib.parse.parse_qs(query or "")
            text = (prm.get("q", [""])[0] or "").strip()
        text = (text or "").strip()
        if not text:
            return self._json(400, {"error": "缺少 q 参数"})
        if not ai_enabled():
            return self._json(503, {"error": "AI 未配置：请在服务端设置 AI_API_KEY（大模型网关 token）",
                                    "gateway": AI_GATEWAY, "model": AI_MODEL})
        if want:
            return self.handle_ai_radio(text, min(30, max(5, want)))
        try:
            plan = ai_plan(text)
        except Exception as e:
            print("[Enhancer] AI 解析失败: %s" % e)
            return self._json(502, {"error": "AI 解析失败: %s" % str(e)[:160]})

        # 多关键词取候选 -> 按吻合度排序 -> 并发探活 -> 只交付能完整播放的
        cand, seen = [], set()
        for kw in plan["keywords"]:
            for s in search_songs(kw, plan["count"]):
                if s.get("id") and s["id"] not in seen:
                    seen.add(s["id"])
                    cand.append(s)
        cand = rank_songs(cand, plan)

        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            flags = list(ex.map(lambda s: quick_playable(s["id"]), cand[:24]))
        for s, ok in zip(cand[:24], flags):
            s["playable"] = bool(ok)

        playable = [s for s in cand[:24] if s["playable"]]
        songs = (playable or cand)[:plan["count"]]
        print("[Enhancer] AI 点歌 %r -> 关键词 %s, 候选 %d, 可播 %d, 交付 %d 首"
              % (text[:24], plan["keywords"], len(cand), len(playable), len(songs)))
        reply = plan.get("reply") or ""
        if playable:
            reply += "（%d 首可完整播放）" % len(playable)
        else:
            reply += "（这些暂时只有试听片段，可能无法完整播放）"
        return self._json(200, {"reply": reply, "plan": plan, "songs": songs,
                                "playable_count": len(playable)})

    # ------------------------------------------------------------ 单曲诊断
    def handle_debug_song(self, query):
        """排查用：说明某首歌会被怎么处理、最终音频真实多长。
        例：/api/debug/song?id=4872687"""
        prm = urllib.parse.parse_qs(query or "")
        sid = (prm.get("id", [""])[0] or "").strip()
        if not sid:
            return self._json(400, {"error": "需要 id 参数"})
        out = {"song_id": sid}
        name, artist, album, dur = song_detail(sid)
        out.update({"name": name, "artist": artist, "album": album, "expected_duration": dur})
        off, _osz = official_url(sid)
        out["official_url_available"] = bool(off)
        out["official_url"] = (off or "")[:110]

        lp = audio_cached(sid)
        if not lp:
            up, src = off, ("official" if off else "")
            if not up and name:
                res = go_resolve(name, artist, album, dur)
                if res and is_http(res.get("url")):
                    up, src = res["url"], "fallback"
                out["fallback_attempts"] = (res or {}).get("attempts")
            out["resolved_via"] = src or "无"
            if up:
                lp, why = fetch_to_disk(sid, up, dur)
                out["fetch_result"] = why
        if lp:
            out["served_file"] = os.path.basename(lp)
            out["size"] = os.path.getsize(lp)
            out["actual_duration"] = round(probe_duration(lp), 1)
            out["verdict"] = ("完整" if (not dur or out["actual_duration"] >= dur - 8) else "片段/不符")
        else:
            out["verdict"] = "不可播放"
        return self._json(200, out)

    # ------------------------------------------------------------ 本地文件播放
    def serve_audio_file(self, path):
        """从本地文件播放，完整支持 Range（拖动进度依赖）"""
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        rng = (self.headers.get("Range") or "").strip()
        if rng.lower().startswith("bytes="):
            part = rng[6:].split(",")[0]
            a, _, b = part.partition("-")
            try:
                if a.strip():
                    start = int(a)
                    end = min(int(b), size - 1) if b.strip() else size - 1
                elif b.strip():
                    start = max(0, size - int(b))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self._cors()
                    self.end_headers()
                    return
                status = 206
            except ValueError:
                start, end, status = 0, size - 1, 200
        length = end - start + 1
        ctype = ("audio/mp4" if path.endswith((".m4a", ".mp4"))
                 else ("audio/flac" if path.endswith(".flac") else "audio/mpeg"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self._cors()
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    c = f.read(min(262144, left))
                    if not c:
                        break
                    self.wfile.write(c)
                    left -= len(c)
        except (BrokenPipeError, ConnectionResetError):
            pass   # 播放器拖动时会主动断开旧连接，属正常

    # ------------------------------------------------------------ 音频代理
    def handle_audio_proxy(self, query):
        prm = urllib.parse.parse_qs(query or "")
        sid = (prm.get("id", [""])[0] or "").strip()
        if not sid:
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        rng_log = self.headers.get("Range") or "全量"
        print("[Enhancer] 播放请求 id=%s 范围=%s UA=%s" % (
            sid, rng_log, (self.headers.get("User-Agent") or "")[:40]))

        # 1) 已整曲落盘 -> 直接本地播放（最快最稳，拖动瞬时响应）
        lp = audio_cached(sid)
        if lp:
            return self.serve_audio_file(lp)

        # 2) 依次尝试所有可用来源，凑到「完整音频」为止。
        #    官方对部分 VIP 曲会返回 30 秒试听直链（且不标 freeTrialInfo），
        #    这种情况必须继续换源，不能直接判为不可播放。
        hit = cache_get(sid)
        if hit and hit[0] == REJECT_MARK:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()
            return
        name, artist, album, dur = song_detail(sid)

        cands, seen, ai_done = [], set(), False
        if hit and hit[0] and hit[0] != REJECT_MARK:
            cands.append((hit[0], hit[3] or "cache"))
            seen.add(hit[0])
        off, _sz = official_url(sid)
        if off and off not in seen:
            cands.append((off, "official"))
            seen.add(off)
        if name:
            res = go_resolve(name, artist, album, dur)
            fb = (res or {}).get("url")
            if is_http(fb) and fb not in seen:
                cands.append((fb, "fallback"))
                seen.add(fb)
            elif not res or not is_http(fb):
                print("[Enhancer] 换源无匹配 %s / %s: %s"
                      % (name, artist, (res or {}).get("attempts")))
                # 规则匹配不到：让模型在「同曲不同写法」的候选里判断（只接受同一录音）
                ai_done = True
                picked = ai_pick_source(name, artist, album, dur)
                if picked:
                    cands.append((picked["url"], "ai-pick"))
                    seen.add(picked["url"])
                    print("[Enhancer] AI 选源候选 %s / %s ← 平台 %s（%s，%s秒）"
                          % (name, artist, picked["source"],
                             picked["reason"], (picked.get("song") or {}).get("duration")))
        outer = NETEASE_OUTER + urllib.parse.quote(sid)
        if outer not in seen:
            cands.append((outer, "netease-outer"))
            seen.add(outer)

        up_url = ""
        rejected = 0
        for cand, src in cands:
            lp, why = fetch_to_disk(sid, cand, dur)
            if lp:
                if src != "cache":
                    build_entry(sid, cand, dur, src)
                    print("[Enhancer] 采用 %s 来源完成落盘 %s (%s)" % (src, sid, name))
                return self.serve_audio_file(lp)
            if why == "duration_rejected":
                rejected += 1
                print("[Enhancer] %s 来源是片段，继续尝试下一个 %s" % (src, sid))
                continue
            print("[Enhancer] %s 来源落盘失败(%s) %s" % (src, why, sid))
            up_url = up_url or cand

        # 规则路径全军覆没（含候选都被判为片段）：给 AI 选源最后一次机会
        if not ai_done and name and rejected:
            picked = ai_pick_source(name, artist, album, dur)
            if picked:
                lp, why = fetch_to_disk(sid, picked["url"], dur)
                if lp:
                    build_entry(sid, picked["url"], dur, "ai-pick")
                    print("[Enhancer] 采用 AI 选源(s)完成落盘 %s (%s) ← %s: %s"
                          % (sid, name, picked["source"], picked["reason"]))
                    return self.serve_audio_file(lp)
                print("[Enhancer] AI 选源落盘失败(%s) %s" % (why, sid))

        if rejected and rejected >= len(cands):
            # 所有来源拿到的都是试听片段：标记不可播放，避免反复重试
            cache_set(sid, REJECT_MARK, 0, 0)
            mark_unplayable(sid)
        if not up_url:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()
            return
        print("[Enhancer] 落盘未成功，退回流式代理 %s" % sid)

        rng = self.headers.get("Range")
        for attempt in (1, 2):
            try:
                hdr = {"User-Agent": "Mozilla/5.0"}
                if rng:
                    hdr["Range"] = rng
                with urllib.request.urlopen(urllib.request.Request(up_url, headers=hdr),
                                            timeout=20) as r:
                    status = r.status if r.status in (200, 206) else 200
                    self.send_response(status)
                    self.send_header("Content-Type", r.headers.get("Content-Type") or "audio/mpeg")
                    self.send_header("Accept-Ranges", "bytes")
                    for k in ("Content-Length", "Content-Range"):
                        v = r.headers.get(k)
                        if v:
                            self.send_header(k, v)
                    self._cors()
                    self.end_headers()
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            except urllib.error.HTTPError as e:
                # 直链是带签名的临时地址，过期后重新解析一次
                if attempt == 1 and e.code in (403, 404, 410):
                    print("[Enhancer] 直链过期(%s)，重新解析 %s" % (e.code, sid))
                    cache_del(sid)
                    name, artist, album, dur = song_detail(sid)
                    res = go_resolve(name, artist, album, dur) if name else None
                    if res and is_http(res.get("url")):
                        up_url = res["url"]
                        build_entry(sid, up_url, dur, "fallback")
                        continue
                self.send_response(502)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            except Exception as e:
                print("[Enhancer] 代理出错: %s" % e)
                try:
                    self.send_response(502)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except Exception:
                    pass
                return

    # ------------------------------------------------------------ 其它接口
    def proxy_upstream(self, path, query):
        code, body = self._up(path, query)
        try:
            data = json.loads(body.decode("utf-8"))
            ungrey_walk(data)
            # 搜索列表：把翻唱/伴奏/片段等变体排到后面，原版优先
            if path in ("/search", "/cloudsearch"):
                res = data.get("result")
                if isinstance(res, dict) and isinstance(res.get("songs"), list):
                    res["songs"] = reorder_search_songs(res["songs"])
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            pass
        self.send_response(code)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/health", "/api/health"):
            try:
                c = _db()
                n = c.execute("SELECT COUNT(*) FROM url_cache").fetchone()[0]
                c.close()
            except Exception:
                n = -1
            return self._json(200, {"status": "ok", "cache": n, "go_adapter": GO_ADAPTER,
                                    "sources": FALLBACK_SOURCES})
        real = p.path[4:] if p.path.startswith("/api/") else p.path
        if real == "/version":
            return self._json(200, {"build": BUILD, "started": START_TS,
                                    "sources": FALLBACK_SOURCES, "cache": CACHE_TTL,
                                    "ai": ai_enabled(), "ai_model": AI_MODEL if ai_enabled() else ""})
        if real == "/song/url":
            return self.handle_song_url(p.query)
        if real == "/audio/proxy":
            return self.handle_audio_proxy(p.query)
        if real == "/debug/song":
            return self.handle_debug_song(p.query)
        if real == "/ai/query":
            return self.handle_ai_query(p.query)
        if real == "/ai/radio":
            qs = urllib.parse.parse_qs(p.query or "")
            q = (qs.get("q", [""])[0] or "").strip()
            try:
                want = int(qs.get("count", ["18"])[0])
            except Exception:
                want = 18
            return self.handle_ai_radio(q, min(30, max(5, want)))
        return self.proxy_upstream(real, p.query)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        real = p.path[4:] if p.path.startswith("/api/") else p.path
        if real == "/client-report":
            return self.handle_client_report()
        if real == "/ai/query":
            ln = int(self.headers.get("Content-Length", 0) or 0)
            return self.handle_ai_query(p.query, self.rfile.read(ln) if ln else b"")
        if real == "/ai/radio":
            ln = int(self.headers.get("Content-Length", 0) or 0)
            try:
                d = json.loads((self.rfile.read(ln) if ln else b"{}").decode("utf-8", "ignore")) or {}
            except Exception:
                d = {}
            try:
                want = int(d.get("count") or 18)
            except Exception:
                want = 18
            return self.handle_ai_radio((d.get("q") or "").strip(), min(30, max(5, want)))
        return self.proxy_upstream(real, p.query)

    def handle_client_report(self):
        """接收前端回报：客户端当前状态与实际播放的音频（用于排查“用户端到底播了什么”）"""
        try:
            ln = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(ln) if ln else b"{}"
            d = json.loads(raw.decode("utf-8", "ignore"))
        except Exception as e:
            print("[Enhancer] 客户端回报解析失败: %s" % e)
            return self._json(200, {"ok": False})
        kind = d.get("kind") or "?"
        if kind == "page":
            print("[Enhancer] 客户端页面 v=%s sw=%s url=%s ua=%s" % (
                d.get("v"), d.get("sw"), (d.get("url") or "")[:80], (d.get("ua") or "")[:60]))
        elif kind == "play":
            print("[Enhancer] 客户端播放 src=%s 时长=%s 秒 位置=%s v=%s ua=%s" % (
                (d.get("src") or "")[:110], d.get("dur"), d.get("t"), d.get("v"),
                (d.get("ua") or "")[:50]))
        else:
            print("[Enhancer] 客户端回报: %s" % json.dumps(d, ensure_ascii=False)[:300])
        return self._json(200, {"ok": True, "build": BUILD})


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    print("[R-Music] Enhancer 启动 端口=%s 适配器=%s 换源=%s" % (PORT, GO_ADAPTER, FALLBACK_SOURCES))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
