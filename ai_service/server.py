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
import threading
import io
import shutil
import http.client
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
AI_MODEL_FALLBACKS = os.getenv("AI_MODEL_FALLBACKS", "")
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
# 音源平台优先级 —— 依据实测（CN 原生 IP，5 首样本 × 11 平台）：
#   kuwo 取到 4/5 真直链（0.1-0.2s）；kugou 5/5 匹配但仅 1/5 出链；qq/netease(库内) 各 1/5；
#   joox/jamendo/bilibili/千千/汽水/5sing 对这 5 首 0-1 匹配（留着不亏，失败都很快）；
#   **migu 每次 30 秒超时**（pd.musicapp.migu.cn 不可达）→ 从列表里摘掉，否则每次失败白等 30 秒。
# 平台能不能用要用真实歌曲实测，不看文档承诺。
DEFAULT_SOURCES = "kuwo,kugou,qq,netease,qianqian,bilibili,joox,soda,fivesing,jamendo"
FALLBACK_SOURCES = os.getenv("FALLBACK_SOURCES", DEFAULT_SOURCES)

# 网易云直链（NetEase 系统）默认不参与取音源（ADR-1：音源以自有 Go 引擎为主力）。
# 需要临时开回最后手段时置 ALLOW_OFFICIAL=1，不必改代码。
ALLOW_OFFICIAL = os.getenv("ALLOW_OFFICIAL", "0") == "1"
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


PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "https://music.1234r.com").rstrip("/")


def song_cover(sid):
    """封面直链（取不到就返回空，不编造）"""
    try:
        with _open(MUSIC_API_UPSTREAM + "/song/detail?ids=" + str(sid),
                   {"User-Agent": "R-Music-Enhancer"}, 5) as r:
            d = json.loads(r.read().decode("utf-8"))
        return ((d.get("songs") or [{}])[0].get("al") or {}).get("picUrl") or ""
    except Exception:
        return ""


def _tracks_from(path, key, sub=None):
    """从网易云上游取一批歌曲（歌单/专辑通用）"""
    try:
        with _open(MUSIC_API_UPSTREAM + path, {"User-Agent": "R-Music-Enhancer"}, 8) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[Enhancer] 取曲目失败 %s: %s" % (path, str(e)[:80]))
        return []
    songs = d.get(key) or []
    if sub:
        songs = ((d.get(sub) or {}).get(key) or [])
    return [s for s in songs if s.get("id")]


def playlist_tracks(pid, limit=100):
    """歌单全部曲目（匿名也能取）"""
    return _tracks_from("/playlist/track/all?id=%s&limit=%d" % (pid, limit), "songs")


def album_tracks(aid):
    return _tracks_from("/album?id=%s" % aid, "songs")


def measure_size(url, sid=None):
    """用 Range 取真实总字节数；取不到返回 0（不编造）"""
    if sid:
        lp = audio_cached(sid)
        if lp:
            return os.path.getsize(lp)
    try:
        req = urllib.request.Request(url, headers=dict(stream_headers(url), Range="bytes=0-0"))
        with urllib.request.urlopen(req, timeout=8) as r:
            cr = r.headers.get("Content-Range") or ""
            r.read(1)
        m = re.search(r"/(\d+)\s*$", cr)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


_go_local = threading.local()


def _pooled_get(base, path, timeout):
    """用「线程内复用」的连接发请求。
    适配器在国内机、经 SSH 隧道访问，每次新建连接要多花几百毫秒握手；
    复用长连接后实测从 900+ms 降到 ~190ms。"""
    base = base.rstrip("/")
    conn = getattr(_go_local, "c:" + base, None)
    if conn is None:
        u = urllib.parse.urlparse(base)
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = cls(u.hostname, u.port or (443 if u.scheme == "https" else 80), timeout=timeout)
        setattr(_go_local, "c:" + base, conn)
    try:
        conn.request("GET", path, headers={"User-Agent": "R-Music-Enhancer",
                                          "Connection": "keep-alive"})
        r = conn.getresponse()
        body = r.read()
        if r.status >= 400:
            raise urllib.error.HTTPError(base + path, r.status, r.reason, r.headers, io.BytesIO(body))
        return json.loads(body)
    except urllib.error.HTTPError:
        raise                       # 业务失败不换地址、不重建连接
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        setattr(_go_local, "c:" + base, None)
        raise


def go_call(path, timeout=60):
    """调用 Go 适配器。主地址（国内隧道）连不上时自动回退到备用地址（本地容器）。
    业务失败（HTTP 404/502 等）不换地址——那是「确实没有」，不是网络问题。"""
    last = None
    for base in [b for b in (GO_ADAPTER, GO_ADAPTER_FALLBACK) if b]:
        try:
            return _pooled_get(base, path, timeout)
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


_ai_model_state = {"model": "", "until": 0.0}


def ai_models():
    """可用模型顺序：主模型 + 备用模型（网关单模型可能因负载 503，必须能自动换）"""
    primary = [AI_MODEL] + [m.strip() for m in AI_MODEL_FALLBACKS.split(",")]
    out = []
    # 最近成功过的模型优先，避免每次都去撞那个正在过载的
    st = _ai_model_state
    if st["model"] and time.time() < st["until"] and st["model"] in primary:
        out.append(st["model"])
    for m in primary:
        if m and m not in out:
            out.append(m)
    return out


def ai_chat(messages, timeout=40, temperature=0.3, json_mode=True):
    """调用大模型网关；返回助手回复文本。
    失败时依次尝试备用模型（网关会因单模型负载返回 503），全部失败才抛异常。"""
    if not ai_enabled():
        raise RuntimeError("未配置 AI_API_KEY")
    last = None
    for model in ai_models():
        body = {"model": model, "messages": messages, "temperature": temperature}
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
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    d = json.loads(r.read().decode("utf-8"))
                txt = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if not isinstance(txt, str) or not txt.strip():
                    raise ValueError("空回复")
                if model != AI_MODEL:
                    print("[Enhancer] 模型降级生效：%s 不可用，改用 %s" % (AI_MODEL, model))
                _ai_model_state.update(model=model, until=time.time() + 300)
                return txt
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "ignore")[:150]
                except Exception:
                    pass
                last = "HTTP %s %s" % (e.code, detail)
                if e.code in (408, 429, 500, 502, 503, 504) and attempt == 1:
                    time.sleep(1.5)          # 过载/限流：稍等重试同一模型
                    continue
                print("[Enhancer] 模型 %s 不可用：%s → 换下一个" % (model, last[:110]))
                break
            except Exception as e:
                last = str(e)[:120]
                print("[Enhancer] 模型 %s 调用异常：%s → 换下一个" % (model, last))
                break
    raise RuntimeError("所有模型均不可用：%s" % last)


PLAN_PROMPT = (
    "你是音乐检索助手。把用户的中文自然语言需求转成 JSON（只输出 JSON，不要解释）：\n"
    '{"keywords":["用于音乐平台搜索的词",...],"artist":"歌手名，没有则空串",'
    '"mood":"情绪或场景，没有则空串","count":5,"reply":"一句简短中文回复"}\n'
    "要求：keywords 用具体可检索的歌名/歌手/主题词，2-3 个，不要整句话；"
    "count 取 3-10；reply 用用户的语言回答。")


SEARCH_ARTIST_PROMPT = (
    "用户在音乐平台只搜了一个词：「%s」。\n"
    "如果这是某首歌的歌名，请给出这首歌**最著名/原唱**的歌手名；\n"
    "如果它本身是歌手名、风格词或专辑名，artist 留空。\n"
    '只输出 JSON：{"song":"歌名","artist":"歌手名","reason":"一句理由"}。\n'
    "拿不准就把 artist 留空——宁可空也不能给错人。")


def upstream_cloudsearch(keyword, limit):
    """直接向上游搜歌，返回原始歌曲对象（字段与前端一致）"""
    u = MUSIC_API_UPSTREAM.rstrip("/") + "/cloudsearch?" + urllib.parse.urlencode(
        {"keywords": keyword, "type": 1, "limit": limit})
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA_BROWSER,
                                                "Referer": "https://music.1234r.com/"})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return ((d.get("result") or {}).get("songs") or [])
    except Exception as e:
        print("[Enhancer] 补搜失败 %r: %s" % (keyword, str(e)[:60]))
        return []


def search_artist_cached(q):
    """查「这个词最可能是谁的歌」的缓存（30 天）"""
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("CREATE TABLE IF NOT EXISTS search_artist (q TEXT PRIMARY KEY, "
                  "artist TEXT, song TEXT, until REAL)")
        row = c.execute("SELECT artist, song, until FROM search_artist WHERE q=?",
                        (q,)).fetchone()
        c.close()
        if row and row[2] and time.time() < row[2]:
            return {"artist": row[0] or "", "song": row[1] or ""}
    except Exception:
        pass
    return None


def search_artist_save(q, artist, song):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("CREATE TABLE IF NOT EXISTS search_artist (q TEXT PRIMARY KEY, "
                  "artist TEXT, song TEXT, until REAL)")
        # 有结果缓存 30 天；没结果 7 天后再问一次
        ttl = 2592000 if artist else 604800
        c.execute("INSERT OR REPLACE INTO search_artist VALUES (?,?,?,?)",
                  (q, artist or "", song or "", time.time() + ttl))
        c.commit()
        c.close()
    except Exception:
        pass


def _bg_search_artist(q):
    """后台问大模型「这个词是谁的歌」，结果进缓存，下次搜索直接用（不拖慢当次搜索）"""
    try:
        out = ai_chat([{"role": "user", "content": SEARCH_ARTIST_PROMPT % q}], temperature=0)
        v = json.loads(_strip_fence(out))
        a = str(v.get("artist") or "").strip()
        # 歌手名里带解释性文字的丢掉
        if len(a) > 20 or "：" in a or ":" in a:
            a = ""
        search_artist_save(q, a, str(v.get("song") or "").strip())
        print("[Enhancer] 搜索词归属: %r -> 歌手=%s（%s）" % (q, a or "无", str(v.get("reason"))[:40]))
    except Exception as e:
        print("[Enhancer] 搜索词归属判定失败 %r: %s" % (q, str(e)[:60]))


def merge_origin_first(extra, base, total):
    """把补搜到的「原唱同名曲」放到最前面，其余保持原顺序，按 id 去重"""
    seen, out = set(), []
    for s in (extra or []) + (base or []):
        sid = str((s or {}).get("id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(s)
    return out[:total] if total else out


def _same_title_artist(s, title, artist):
    """这首歌是否就是「目标歌手的同名曲」"""
    if _norm_loose((s or {}).get("name")) != _norm_loose(title):
        return False
    ar = " ".join(a.get("name", "") for a in ((s or {}).get("ar") or []))
    na, nar = _norm_loose(artist), _norm_loose(ar)
    return bool(na and nar and (na in nar or nar in na))


def _has_artist_title(songs, title, artist):
    """列表里是否已经有「这个歌手的这首同名曲」"""
    nt, na = _norm_loose(title), _norm_loose(artist)
    for s in (songs or []):
        if _norm_loose((s or {}).get("name")) != nt:
            continue
        ar = " ".join(a.get("name", "") for a in ((s or {}).get("ar") or []))
        if na and _norm_loose(ar) and (na in _norm_loose(ar) or _norm_loose(ar) in na):
            return True
    return False


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


_prewarm_lock = threading.Lock()
_prewarming = set()
_prewarm_stamps = []

PREWARM_PER_LIST = 2            # 每个列表最多预热几首（每首个 ~4MB，别浪费带宽）
PREWARM_WINDOW = 600            # 10 分钟窗口内最多预热次数
PREWARM_MAX = 12


def _prewarm_allowed():
    now = time.time()
    with _prewarm_lock:
        while _prewarm_stamps and now - _prewarm_stamps[0] > PREWARM_WINDOW:
            _prewarm_stamps.pop(0)
        return len(_prewarm_stamps) < PREWARM_MAX


# 允许的来路（防外站把我们的音频代理当免费 CDN）
ALLOWED_REFERERS = tuple(x for x in os.getenv(
    "ALLOWED_REFERERS", "music.1234r.com,64.83.34.204,localhost,127.0.0.1").split(",") if x.strip())


def load_internal_token():
    try:
        with open(os.path.join(DATA_DIR, "internal_token.txt")) as f:
            return f.read().strip()
    except Exception:
        return ""


def _private_ip(ip):
    ip = (ip or "").strip()
    if not ip:
        return False
    return (ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172.16.")
            or ip.startswith("172.17.") or ip.startswith("172.18.") or ip.startswith("172.19.")
            or ip.startswith("127.") or ip.startswith("::1") or ip == "172.20.0.1")


def _private_host(host):
    """局域网/本机来源：自家网络的访问（含本地预览、手机连同一 Wi-Fi）都属于自己"""
    h = (host or "").lower()
    if h in ("localhost", "::1") or h.endswith(".local"):
        return True
    if h.startswith("127.") or h.startswith("10.") or h.startswith("192.168."):
        return True
    if h.startswith("172."):
        try:
            return 16 <= int(h.split(".")[1]) <= 31
        except Exception:
            return False
    return False


AUDIO_MAGIC = (
    (b"fLaC", "audio/flac"),
    (b"ID3", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
    (b"RIFF", "audio/wav"),
)


def sniff_audio_type(head):
    """按容器魔数判断音频类型（上游常把 flac 标成 octet-stream，播放器会选错解码器）"""
    if head[:4] == b"\xff\xf1" or head[:2] == b"\xff\xfb" or head[:2] == b"\xff\xf3":
        return "audio/mpeg"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    for magic, ctype in AUDIO_MAGIC:
        if head.startswith(magic):
            return ctype
    return ""


def probe_audio_headers(url):
    """HEAD 用：只发一个 16 字节的 Range 请求，拿真实类型与总长度，不拉整曲"""
    try:
        h = stream_headers(url)
        h["Range"] = "bytes=0-15"
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=15) as r:
            head = r.read(16) or b""
            cr = r.headers.get("Content-Range") or ""
            ct = r.headers.get("Content-Type") or ""
            total = 0
            if "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[1])
                except Exception:
                    total = 0
            if not total:
                try:
                    total = int(r.headers.get("Content-Length") or 0)
                except Exception:
                    total = 0
            sniffed = sniff_audio_type(head)
            if sniffed:
                ct = sniffed
            elif not ct.startswith("audio/"):
                ct = "audio/mpeg"
            return ct, total
    except Exception as e:
        print("[Enhancer] HEAD 探测失败: %s" % str(e)[:90])
        return "audio/mpeg", 0


def referer_allowed(handler):
    """带 Referer 但不是我们自己站点、也不是局域网来源的 → 拒绝（防外站盗链）。
    没带 Referer 的放行（自家播放器/诊断工具）。
    注意：本地预览用局域网地址访问时 Referer 是 192.168.x.x，必须放行，
    否则「防盗链」会把自家手机挡在门外。"""
    ref = handler.headers.get("Referer") or handler.headers.get("Origin") or ""
    if not ref:
        return True
    try:
        host = urllib.parse.urlparse(ref).hostname or ""
    except Exception:
        return True
    if not host:
        return True
    if any(a.strip() and a.strip() in host for a in ALLOWED_REFERERS):
        return True
    return _private_host(host)


RECHECK_EVERY = int(os.getenv("RECHECK_EVERY", "1800"))    # 每 30 分钟复核一批
RECHECK_BATCH = int(os.getenv("RECHECK_BATCH", "3"))


# ---------------------------------------------------------------- 口味记忆
def _taste_db():
    c = sqlite3.connect(CACHE_DB)
    c.execute("CREATE TABLE IF NOT EXISTS taste (song_id TEXT, action TEXT, played INT, "
              "dur INT, ts REAL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_taste ON taste(action, ts)")
    c.execute("CREATE TABLE IF NOT EXISTS song_meta (song_id TEXT PRIMARY KEY, name TEXT, "
              "artist TEXT, ts REAL)")
    return c


def meta_remember(sid, name, artist):
    """记住歌曲元数据，供口味统计时本地取用（避免为了显示名字去打上游接口）"""
    if not sid or not name:
        return
    try:
        c = _taste_db()
        c.execute("INSERT OR REPLACE INTO song_meta VALUES (?,?,?,?)",
                  (str(sid), name, artist or "", time.time()))
        c.commit()
        c.close()
    except Exception:
        pass


def meta_of(sid):
    try:
        c = _taste_db()
        row = c.execute("SELECT name, artist FROM song_meta WHERE song_id=?",
                        (str(sid),)).fetchone()
        c.close()
        return (row[0], row[1]) if row else (None, None)
    except Exception:
        return (None, None)


# 收藏也记进同一张口味表：它是比"听满 30 秒"强得多的正反馈
LIKE_ACTIONS = ("like", "unlike")


def record_taste(sid, action, played=0, dur=0):
    """记录一次真实收听行为：play=听了、skip=没听进去就切了、like/unlike=收藏与否"""
    if not sid or action not in ("play", "skip") + LIKE_ACTIONS:
        return
    try:
        c = _taste_db()
        c.execute("INSERT INTO taste VALUES (?,?,?,?,?)",
                  (str(sid), action, int(played or 0), int(dur or 0), time.time()))
        c.commit()
        c.close()
    except Exception:
        pass


def favorites(limit=500):
    """当前收藏（每首取最后一次 like/unlike：最后一次是 like 才算收藏）"""
    try:
        c = _taste_db()
        rows = c.execute(
            "SELECT song_id, action, MAX(ts) t FROM taste WHERE action IN ('like','unlike') "
            "GROUP BY song_id HAVING action='like' ORDER BY t DESC LIMIT ?", (limit,)).fetchall()
        c.close()
    except Exception:
        return []
    out = []
    for sid, _a, t in rows:
        n, ar = meta_of(sid)
        out.append({"id": sid, "name": n or "", "artist": ar or "", "liked_at": t})
    return out


def liked_artists(limit=10):
    """收藏里出现的歌手（口味上下文里权重最高的一类信号）"""
    got = []
    for f in favorites(limit * 3):
        for x in [p.strip() for p in (f.get("artist") or "").replace("&", "/").replace(",", "/").split("/") if p.strip()]:
            if x not in got:
                got.append(x)
        if len(got) >= limit:
            break
    return got


def taste_context(days=30, top=6):
    """给大模型的口味上下文：常听歌手 + 常被跳过的歌。没有数据时返回空串。"""
    try:
        since = time.time() - days * 86400
        c = _taste_db()
        plays = c.execute(
            "SELECT song_id, COUNT(*) n, SUM(played) s, MAX(dur) d FROM taste "
            "WHERE action='play' AND ts>? GROUP BY song_id ORDER BY n DESC, s DESC LIMIT ?",
            (since, top)).fetchall()
        skips = c.execute(
            "SELECT song_id, COUNT(*) n FROM taste WHERE action='skip' AND ts>? "
            "GROUP BY song_id ORDER BY n DESC LIMIT ?", (since, top)).fetchall()
        total = c.execute("SELECT COUNT(*) FROM taste WHERE ts>?", (since,)).fetchone()[0]
        c.close()
    except Exception:
        return ""
    if total < 3:
        return ""
    def label(sid):
        n, a = meta_of(sid)
        return "%s%s" % (n or sid, ("-" + a) if a else "")
    liked = liked_artists(8)          # 收藏过的歌手，权重最高
    artists = list(liked)
    for sid, _n, _s, _d in plays:
        _nm, ar = meta_of(sid)
        for x in [p.strip() for p in (ar or "").replace("&", "/").replace(",", "/").split("/") if p.strip()]:
            if x not in artists:
                artists.append(x)
    parts = []
    favs = favorites(8)
    if favs:      # 明确收藏 = 最强信号，放在最前面
        parts.append("明确收藏（很喜欢，优先满足）："
                     + "、".join("%s%s" % (f["name"], ("-" + f["artist"]) if f["artist"] else "") for f in favs[:6]))
    if plays:
        parts.append("常听：" + "、".join(label(s) for s, _n, _s, _d in plays[:5]))
    if artists:
        parts.append("偏好歌手：" + "、".join(artists[:6]))
    if skips:
        parts.append("经常跳过（不要再推荐）：" + "、".join(label(s) for s, _n in skips[:5]))
    return "；".join(parts)


def taste_stats():
    try:
        c = _taste_db()
        r = c.execute("SELECT action, COUNT(*) FROM taste GROUP BY action").fetchall()
        c.close()
        return dict(r)
    except Exception:
        return {}


def unplayable_expiring(limit):
    """挑最快到期的几条「无音源」记录来复核（越接近到期越该重试）"""
    try:
        c = _mark_db()
        rows = c.execute("SELECT song_id, until FROM unplayable ORDER BY until ASC LIMIT ?",
                         (limit,)).fetchall()
        c.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def recheck_worker():
    """后台主动复核：以前判为「全网无完整音源」的歌，定期重新探一次。
    平台补上版权后能自动恢复可播，不需要人工介入。"""
    while True:
        try:
            time.sleep(RECHECK_EVERY)
            ids = unplayable_expiring(RECHECK_BATCH)
            if not ids:
                continue
            print("[Enhancer] 主动复核 %d 首无音源曲目: %s" % (len(ids), ids))
            for sid in ids:
                try:
                    # 清掉旧的否定判定，否则复核会命中缓存直接返回 False
                    cache_del(sid)
                    c = sqlite3.connect(CACHE_DB)
                    c.execute("DELETE FROM probeable WHERE song_id=?", (str(sid),))
                    c.commit()
                    c.close()
                    if quick_playable(sid):
                        clear_unplayable(sid)
                        print("[Enhancer] 复核发现已可播，恢复显示: %s" % sid)
                        prewarm_song(sid)
                    else:
                        mark_unplayable(sid)      # 续期，过段时间再试
                except Exception as e:
                    print("[Enhancer] 复核异常 %s: %s" % (sid, str(e)[:60]))
        except Exception as e:
            print("[Enhancer] 复核线程异常: %s" % str(e)[:80])


def clear_unplayable(sid):
    """解除「无音源」标记，让列表重新点亮"""
    try:
        c = _mark_db()
        c.execute("DELETE FROM unplayable WHERE song_id=?", (str(sid),))
        c.commit()
        c.close()
    except Exception:
        pass


def prewarm_song(sid):
    """后台把一首歌解析并落盘，让用户点下去几乎立刻能响"""
    sid = str(sid or "").strip()
    if not sid or audio_cached(sid) or is_unplayable(sid):
        return
    if not _prewarm_allowed():
        return
    with _prewarm_lock:
        if sid in _prewarming:
            return
        _prewarming.add(sid)
        _prewarm_stamps.append(time.time())

    def work():
        try:
            name, artist, album, dur = song_detail(sid)
            if not name:
                return
            cands = []
            off, _sz = official_url(sid)
            if is_http(off):
                cands.append(off)
            res = go_resolve(name, artist, album, dur)
            if is_http((res or {}).get("url")):
                cands.append(res["url"])
            for c in cands:
                lp, why = fetch_to_disk(sid, c, dur)
                if lp:
                    build_entry(sid, c, dur, "prewarm")
                    print("[Enhancer] 预热完成 %s (%s)" % (sid, name))
                    return
            print("[Enhancer] 预热未成功 %s (%s)" % (sid, name))
        except Exception as e:
            print("[Enhancer] 预热异常 %s: %s" % (sid, str(e)[:60]))
        finally:
            with _prewarm_lock:
                _prewarming.discard(sid)

    threading.Thread(target=work, daemon=True).start()


def collect_song_ids(node, limit, out=None):
    """从上游返回里挑出歌曲 id（用于列表预热）"""
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(node, list):
        for x in node:
            collect_song_ids(x, limit, out)
    elif isinstance(node, dict):
        if node.get("id") and (node.get("ar") or node.get("al")) and node.get("name"):
            out.append(str(node["id"]))
            if len(out) >= limit:
                return out
        for v in node.values():
            collect_song_ids(v, limit, out)
    return out[:limit]


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


CONTINUE_PROMPT = (
    "用户正在连续收听音乐，当前这首是：歌名=%s 歌手=%s 专辑=%s\n"
    "请给出 6-8 个检索词，用来找**风格/氛围/年代/语种相近、但不重复**的歌，让连续播放不断档。\n"
    "要求：不要出现当前这首歌自己的名字；可以用同歌手的其他代表作、同风格歌手、"
    "同年代同语种、同一场景。\n"
    '只输出 JSON：{"title":"电台名(12字内)","keywords":["检索词",...],"reply":"一句话"}。')


def ai_continue_plan(name, artist, album, ctx=""):
    """让大模型基于当前曲目给出「接着听什么」的检索词"""
    out = ai_chat([{"role": "user", "content": CONTINUE_PROMPT % (name, artist, album or "")
                    + (("\n【用户口味】" + ctx) if ctx else "")}], temperature=0.55)
    plan = json.loads(_strip_fence(out))
    kws = [str(k) for k in (plan.get("keywords") or []) if str(k).strip()]
    if not kws:
        kws = [artist or name]
    plan["keywords"] = kws[:8]
    return plan


ASK_PROMPT = (
    "判断用户这句话想让音乐播放器做什么。只输出 JSON（不要解释）：\n"
    '{"intent":"play|radio|continue|control|unknown",'
    '"query":"用于检索的词（play/radio 时给）",'
    '"control":"next|prev|pause|resume|volume_up|volume_down|mute|shuffle",'
    '"reply":"一句简短中文回复"}\n'
    "intent 含义：\n"
    "  play     = 想听具体的歌/歌手/专辑（例如「放周杰伦的晴天」）\n"
    "  radio    = 想要一类歌单/场景/情绪（例如「深夜写代码听的」）\n"
    "  continue = 想接着听类似的、换点别的（例如「再来点类似的」）\n"
    "  control  = 控制正在播放（切歌/暂停/继续/音量/随机）\n"
    "  unknown  = 无法判断\n"
    "注意：控制类必须只填 control；不要把它当搜索词。")


def ai_ask_plan(text):
    out = ai_chat([{"role": "user", "content": ASK_PROMPT + "\n用户说：" + text}], temperature=0)
    v = json.loads(_strip_fence(out))
    return v if isinstance(v, dict) else {}


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


AUDIO_MAX_BYTES = int(os.getenv("AUDIO_MAX_BYTES", str(2 * 1024 ** 3)))   # 缓存体积上限 2GB
DISK_FREE_MIN_GB = float(os.getenv("DISK_FREE_MIN_GB", "8"))              # 剩余空间低于此值就狠清
DISK_CHECK_EVERY = 300                                                    # 最快 5 分钟检查一次磁盘


def disk_usage(path=DATA_DIR):
    try:
        u = shutil.disk_usage(path)
        return {"total_gb": u.total / 1e9, "free_gb": u.free / 1e9,
                "used_pct": (u.used / u.total) * 100 if u.total else 0}
    except Exception:
        return {"total_gb": 0, "free_gb": 0, "used_pct": 0}


def audio_cache_stats():
    try:
        fs = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR)
              if f.endswith(AUDIO_EXTS)]
        return {"files": len(fs), "mb": round(sum(os.path.getsize(f) for f in fs) / 1048576, 1)}
    except Exception:
        return {"files": 0, "mb": 0}


_last_disk_check = [0.0]


def evict_audio(force=False):
    """双重约束：文件数上限 + 体积上限；磁盘剩余过少时额外狠清。
    返回是否真的删了东西。"""
    now = time.time()
    if not force and now - _last_disk_check[0] < DISK_CHECK_EVERY:
        return False
    _last_disk_check[0] = now
    removed = 0
    try:
        fs = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR)
              if f.endswith(AUDIO_EXTS)]
        if not fs:
            return False
        fs.sort(key=os.path.getmtime)
        sizes = {}
        try:
            sizes = {f: os.path.getsize(f) for f in fs}
        except Exception:
            pass
        du = disk_usage()
        # 磁盘吃紧：把缓存砍到上限的四分之一，优先保命
        if du["free_gb"] and du["free_gb"] < DISK_FREE_MIN_GB:
            keep = max(30, AUDIO_MAX_FILES // 4)
            print("[Enhancer] 磁盘剩 %.1fG(<%.0fG)，缓存收紧到 %d 首"
                  % (du["free_gb"], DISK_FREE_MIN_GB, keep))
            for f in fs[:max(0, len(fs) - keep)]:
                try:
                    os.remove(f)
                    removed += 1
                except Exception:
                    pass
            return removed > 0
        over_files = max(0, len(fs) - AUDIO_MAX_FILES)
        total = sum(sizes.values()) if sizes else 0
        over_bytes = max(0, total - AUDIO_MAX_BYTES)
        drop = over_files
        acc = 0
        for f in fs[over_files:]:
            if acc >= over_bytes:
                break
            acc += sizes.get(f, 0)
            drop += 1
        for f in fs[:drop]:
            try:
                os.remove(f)
                removed += 1
            except Exception:
                pass
        if removed:
            print("[Enhancer] 缓存淘汰 %d 首（文件 %d/上限%d，体积 %.0fMB/上限%.0fMB）"
                  % (removed, len(fs), AUDIO_MAX_FILES, total / 1048576,
                     AUDIO_MAX_BYTES / 1048576))
    except Exception as e:
        print("[Enhancer] 缓存淘汰异常: %s" % str(e)[:70])
    return removed > 0


# 国内平台直链普遍校验 Referer：实测酷我系直链缺 Referer 会 403 Forbidden。
# 按 URL 主机补上对应站点的 Referer，取流（落盘/Range 探测/流式代理）三处统一使用。
PLATFORM_REFERER = (
    ("kuwo.cn", "http://www.kuwo.cn/"),
    ("kugou.com", "http://www.kugou.com/"),
    ("y.qq.com", "https://y.qq.com/"),
    ("qq.com", "https://y.qq.com/"),
    ("music.163.com", "https://music.163.com/"),
    ("migu.cn", "http://music.migu.cn/"),
    ("bilibili.com", "https://www.bilibili.com/"),
    ("bilivideo.com", "https://www.bilibili.com/"),
    ("joox.com", "https://www.joox.com/"),
    ("douyin.com", "https://music.douyin.com/"),
    ("soda", "https://music.douyin.com/"),
)


def stream_headers(url):
    """取流请求头：平台直链大多校验 Referer，缺了会 403"""
    h = {"User-Agent": UA_BROWSER, "Accept": "*/*"}
    u = (url or "").lower()
    for key, ref in PLATFORM_REFERER:
        if key in u:
            h["Referer"] = ref
            break
    return h


def _adapter_bases():
    """国内适配器地址（主 + 备用）"""
    return [b.rstrip("/") for b in (GO_ADAPTER, GO_ADAPTER_FALLBACK) if b]


def _via_adapter_url(up_url):
    """把音频地址包成「经国内适配器代抓」的 URL"""
    return "/fetch?url=" + urllib.parse.quote(up_url, safe="")


def fetch_to_disk(sid, up_url, expected=0, timeout=90, via_adapter=False):
    """整首音频落盘。签名直链时效很短，落盘后播放与拖动都不再依赖它。

    via_adapter=True：改由国内适配器的 /fetch 代抓。
    为什么需要：实测部分平台直链与**国内 IP 绑定**（千千/dmhmusic 系：东京出口 403、国内出口 206），
    另有些平台对海外 IP 只返回 30 秒试听片段 —— 这类失败不是"没音源"，而是出口不对。
    代价是隧道带宽只有 ~335KB/s（对比东京直取 9MB/s），所以只在直取失败时用。
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)
    tmp = os.path.join(AUDIO_DIR, sid + ".part")

    targets = []
    if via_adapter:
        for base in _adapter_bases():
            targets.append((base + _via_adapter_url(up_url), {"User-Agent": UA_BROWSER, "Accept": "*/*"}))
        timeout = max(timeout, 600)          # 隧道慢，给足时间
    else:
        targets.append((up_url, stream_headers(up_url)))

    last = "fetch_error"
    for req_url, hdrs in targets:
        try:
            req = urllib.request.Request(req_url, headers=hdrs)
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
                last = "too_small"
                continue
            final = os.path.join(AUDIO_DIR, sid + ext)
            os.replace(tmp, final)
            # 以真实容器为准纠正扩展名（实测出现 .mp3 里装 M4A/FLAC 的情况，播放器会因此解不开）
            sniffed = sniff_audio_type(open(final, "rb").read(16))
            want = {"audio/flac": ".flac", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
                    "audio/ogg": ".ogg", "audio/wav": ".wav"}.get(sniffed, "")
            if want and want != ext and ext in (".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".wav"):
                fixed = os.path.join(AUDIO_DIR, sid + want)
                os.replace(final, fixed)
                print("[Enhancer] 扩展名不符(%s->%s)，已按真实容器改名 %s" % (ext, want, sid))
                final = fixed
            ok, actual = duration_ok(final, expected)
            if not ok:
                try:
                    os.remove(final)
                except Exception:
                    pass
                print("[Enhancer] 时长不符被拒：%s 期望 %.0f 秒，实际只有 %.1f 秒（试听片段或占位音频）"
                      % (sid, expected or 0, actual))
                last = "duration_rejected"
                continue
            print("[Enhancer] 整曲落盘 %s (%d 字节 %s, 实测 %.1f 秒)%s"
                  % (sid, n, ext, actual, "（国内出口）" if via_adapter else ""))
            evict_audio()
            return final, "ok"
        except Exception as e:
            last = "fetch_error"
            print("[Enhancer] 落盘失败 %s%s: %s"
                  % (sid, "（国内出口）" if via_adapter else "", str(e)[:90]))
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    return None, last


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


HEAD_ONLY = {}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _wbody(self, b):
        """写响应体；HEAD 请求只发头不发体（否则 keep-alive 的帧会错位）"""
        if HEAD_ONLY.get(id(self)):
            return
        self.wfile.write(b)

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
        self._wbody(b)

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
    def _continue_payload(self, query, body=None):
        """AI 续播（纯函数版，返回 (状态码, 数据)，便于被统一指令复用）"""
        prm = urllib.parse.parse_qs(query or "")
        sid = (prm.get("sid", [""])[0] or "").strip()
        try:
            want = int(prm.get("want", ["6"])[0])
        except Exception:
            want = 6
        if not ai_enabled():
            return 503, {"error": "AI 未配置"}
        name, artist, album, dur = song_detail(sid) if sid else ("", "", "", 0)
        if not name:
            return 400, {"error": "缺少有效的 sid（当前曲目 id）"}
        exclude = set()
        for x in (prm.get("exclude", [""])[0] or "").split(","):
            x = x.strip()
            if x:
                exclude.add(x)
        if sid:
            exclude.add(str(sid))
        ctx = taste_context()
        try:
            plan = ai_continue_plan(name, artist, album, ctx)
        except Exception as e:
            print("[Enhancer] AI 续播解析失败: %s" % str(e)[:80])
            return 502, {"error": "AI 解析失败: %s" % str(e)[:120]}
        songs, _ = self._ai_collect(plan["keywords"], {"artist": artist}, per_kw=8, limit=want + len(exclude))
        songs = [s for s in songs if str(s.get("id")) not in exclude][:want]
        print("[Enhancer] AI 续播 ← 《%s》%s -> %d 首（关键词 %s）"
              % (name, artist, len(songs), plan["keywords"][:4]))
        return 200, {"title": plan.get("title") or "继续播放",
                     "reply": plan.get("reply") or "",
                     "keywords": plan["keywords"], "songs": songs,
                     "seed": {"id": sid, "name": name, "artist": artist}}

    def handle_ai_continue(self, query, body=None):
        return self._json(*self._continue_payload(query, body))

    def handle_ai_ask(self, body):
        """统一指令入口：一句话判断意图（点歌/电台/续播/控制）并分派"""
        try:
            d = json.loads((body or b"{}").decode("utf-8", "ignore")) or {}
        except Exception:
            d = {}
        text = (d.get("q") or "").strip()
        seed = str(d.get("seed") or "")
        exclude = ",".join(str(x) for x in (d.get("exclude") or []))
        if not text:
            return self._json(400, {"error": "缺少 q"})
        if not ai_enabled():
            return self._json(503, {"error": "AI 未配置"})
        try:
            plan = ai_ask_plan(text)
        except Exception as e:
            return self._json(502, {"error": "AI 解析失败: %s" % str(e)[:120]})
        intent = (plan.get("intent") or "unknown").lower()
        reply = str(plan.get("reply") or "")[:80]
        print("[Enhancer] AI 指令 %r -> intent=%s control=%s"
              % (text[:24], intent, plan.get("control")))
        if intent == "control":
            return self._json(200, {"intent": "control", "control": plan.get("control") or "next",
                                    "reply": reply})
        if intent == "continue":
            q = "sid=%s&want=6&exclude=%s" % (urllib.parse.quote(seed), urllib.parse.quote(exclude))
            code, payload = self._continue_payload(q)
            payload["intent"] = "continue"
            return self._json(code, payload)
        if intent == "radio":
            code, payload = self._radio_payload(plan.get("query") or text, 15)
            payload["intent"] = "radio"
            return self._json(code, payload)
        # play / unknown 都按「点歌」走，拿不到歌再退化成电台
        code, payload = self._query_payload("q=" + urllib.parse.quote(plan.get("query") or text))
        if not payload.get("songs"):
            code2, payload2 = self._radio_payload(plan.get("query") or text, 12)
            payload2["intent"] = "radio"
            return self._json(code2, payload2)
        payload["intent"] = "play"
        if reply and not payload.get("reply"):
            payload["reply"] = reply
        return self._json(code, payload)

    def _radio_payload(self, text, want=18):
        """一句话生成整张歌单（纯函数版，返回 (状态码, 数据)）"""
        ctx = taste_context()
        if ctx:
            print("[Enhancer] 带入口味上下文: %s" % ctx[:140])
        ask = text + (("\n\n【用户口味参考，用来提高命中偏好，别生硬照搬，也别全用这些】" + ctx)
                      if ctx else "")
        try:
            plan = ai_radio_plan(ask)
        except Exception as e:
            print("[Enhancer] AI 电台解析失败: %s" % e)
            return 502, {"error": "AI 解析失败: %s" % str(e)[:160]}
        songs, _ = self._ai_collect(plan["keywords"], plan, per_kw=8, limit=want)
        if len(songs) < min(8, want):
            # 不够就再要一轮关键词（最多补一次，避免无限循环）
            try:
                more = ai_radio_plan(ask + "（再给 6 个不同的检索词，避免与上面重复）")
                extra, _ = self._ai_collect(more["keywords"], plan, per_kw=8,
                                            limit=want - len(songs))
                have = {s["id"] for s in songs}
                songs += [s for s in extra if s["id"] not in have]
            except Exception as e:
                print("[Enhancer] AI 电台补词失败: %s" % e)
        title = plan.get("title") or "AI 电台"
        reply = plan.get("reply") or ""
        # 让大模型对真实可播歌单做策展（取舍 + 排序 + 命名）；把口味一并给它
        cur = ai_curate(text + (("\n【用户口味】" + ctx) if ctx else ""), songs)
        if cur:
            title = cur["title"] or title
            reply = cur["reply"] or reply
            songs = cur["songs"]
        songs = songs[:want]
        print("[Enhancer] AI 电台 %r -> %d 首可播（关键词 %d 个，策展=%s）"
              % (text[:24], len(songs), len(plan["keywords"]), bool(cur)))
        return 200, {"title": title, "reply": reply,
                     "curated": bool(cur), "picked": (cur or {}).get("picked"),
                     "plan": {"keywords": plan["keywords"]},
                     "songs": songs, "playable_count": len(songs)}

    def handle_ai_radio(self, text, want=18):
        return self._json(*self._radio_payload(text, want))

    # ------------------------------------------------------------ AI 点歌
    def _query_payload(self, query, body=None):
        """自然语言点歌（纯函数版，返回 (状态码, 数据)）"""
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
            return 400, {"error": "缺少 q 参数"}
        if not ai_enabled():
            return 503, {"error": "AI 未配置：请在服务端设置 AI_API_KEY（大模型 gateway token）",
                         "gateway": AI_GATEWAY, "model": AI_MODEL}
        if want:
            return self.handle_ai_radio(text, min(30, max(5, want)))
        _t = taste_context()
        try:
            plan = ai_plan(text + (("\n【用户口味参考】" + _t) if _t else ""))
        except Exception as e:
            print("[Enhancer] AI 解析失败: %s" % e)
            return 502, {"error": "AI 解析失败: %s" % str(e)[:160]}

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
        _ctx = taste_context()
        if _ctx:
            print("[Enhancer] 点歌带入口味: %s" % _ctx[:100])
        print("[Enhancer] AI 点歌 %r -> 关键词 %s, 候选 %d, 可播 %d, 交付 %d 首"
              % (text[:24], plan["keywords"], len(cand), len(playable), len(songs)))
        reply = plan.get("reply") or ""
        if playable:
            reply += "（%d 首可完整播放）" % len(playable)
        else:
            reply += "（这些暂时只有试听片段，可能无法完整播放）"
        return 200, {"reply": reply, "plan": plan, "songs": songs,
                     "playable_count": len(playable)}

    def handle_ai_query(self, query, body=None):
        return self._json(*self._query_payload(query, body))

    # ------------------------------------------------------------ 单曲诊断
    def handle_debug_song(self, query):
        """排查用：说明某首歌会被怎么处理、最终音频真实多长。
        例：/api/debug/song?id=4872687
        会暴露内部落盘信息，因此仅限内网来源或带内部令牌访问。"""
        tok = load_internal_token()
        given = (self.headers.get("X-RM-Token") or "").strip()
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        client = fwd or (self.headers.get("X-Real-IP") or "").strip() or self.client_address[0]
        if not (tok and given and given == tok) and not _private_ip(client):
            return self._json(403, {"error": "该接口仅限内网或带内部令牌访问"})
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
        if HEAD_ONLY.get(id(self)):
            return                      # HEAD：头部已发完，不读文件
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
    # ------------------------------------------------------------ Music Assistant / HA 桥
    def _ma_pick_sid(self, prm):
        """把「歌曲 id」或「一句话」解析成一个可播放的歌曲 id"""
        sid = (prm.get("id", [""])[0] or "").strip()
        if sid:
            return sid
        q = (prm.get("q", [""])[0] or "").strip()
        if not q:
            return ""
        want = 0
        try:
            want = int(prm.get("i", ["0"])[0])
        except Exception:
            want = 0
        songs = []
        is_url = q.startswith("http")
        if not is_url:
            try:
                _code, payload = self._query_payload("q=" + urllib.parse.quote(q))
                songs = payload.get("songs") or []
            except Exception as e:
                print("[Enhancer] MA 桥点歌失败: %s" % str(e)[:90])
            if not songs:      # 点歌没命中就退化成电台
                try:
                    _code, payload = self._radio_payload(q, 8)
                    songs = payload.get("songs") or []
                except Exception as e:
                    print("[Enhancer] MA 桥电台失败: %s" % str(e)[:90])
        # 也允许直接传一个音频直链
        if is_url:
            return "url:" + q
        if not songs:
            return ""
        idx = max(0, min(want, len(songs) - 1))
        # 同一批结果里优先没有版本标记的（用户没点名要 Live/翻唱/伴奏时别给这些）
        if not any(m in q.lower() for m in ("live", "现场", "翻唱", "伴奏", "remix")):
            clean = [i for i, s in enumerate(songs) if not _markers(s.get("name") or "")]
            if clean:
                idx = clean[min(idx, len(clean) - 1)]
        return str(songs[idx].get("id") or "")

    def handle_ma_play(self, query):
        """给 Music Assistant / HA 用的「一个 URL 即一句话点歌」：
        /api/ma/play?q=周杰伦的晴天 或 ?id=186016 —— 直接把音频流出去（支持 Range）"""
        prm = urllib.parse.parse_qs(query or "")
        sid = self._ma_pick_sid(prm)
        if not sid:
            print("[Enhancer] MA 桥未找到可播放曲目 q=%s" % (prm.get("q", [""])[0])[:40])
            self.send_response(404)
            self.send_header("Content-Type", "text/plain;charset=utf-8")
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()
            return
        if sid.startswith("url:"):
            return self.handle_audio_proxy("id=" + urllib.parse.quote(sid[4:]))
        print("[Enhancer] MA 桥播放 id=%s（q=%s）"
              % (sid, (prm.get("q", [""])[0] or "")[:30]))
        return self.handle_audio_proxy("id=" + sid)

    def handle_ma_resolve(self, query):
        """返回 JSON 元数据（HA 脚本/传感器要用 URL 时用这个）"""
        prm = urllib.parse.parse_qs(query or "")
        sid = self._ma_pick_sid(prm)
        if not sid:
            return self._json(404, {"ok": False, "error": "没找到可播放的曲目"})
        name, artist, album, dur = song_detail(sid)
        return self._json(200, {
            "ok": True, "id": sid, "title": name, "artist": artist, "album": album,
            "duration": dur, "cover": song_cover(sid),
            "url": "%s/api/audio/proxy?id=%s" % (PUBLIC_BASE, sid),
            "stream": "%s/api/ma/play?id=%s" % (PUBLIC_BASE, sid),
        })

    def handle_ma_m3u(self, query):
        """M3U 播放清单：支持一句话电台(?q=)、歌单(?pid=)、专辑(?aid=)"""
        prm = urllib.parse.parse_qs(query or "")
        songs = []
        q = (prm.get("q", [""])[0] or "").strip()
        pid = (prm.get("pid", [""])[0] or "").strip()
        aid = (prm.get("aid", [""])[0] or "").strip()
        if pid:
            songs = playlist_tracks(pid)
        elif aid:
            songs = album_tracks(aid)
        elif q:
            _code, payload = self._radio_payload(q, 20)
            songs = payload.get("songs") or []
        out = ["#EXTM3U"]
        for s in songs[:50]:
            ar = "、".join(a.get("name", "") for a in (s.get("ar") or []))
            out.append("#EXTINF:%d,%s - %s" % (int(s.get("dt", 0) // 1000), ar, s.get("name", "")))
            out.append("%s/api/audio/proxy?id=%s" % (PUBLIC_BASE, s.get("id")))
        body = ("\n".join(out) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "audio/x-mpegurl;charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self._wbody(body)

    def _send_audio_head(self, ctype, size):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self._cors()
        self.end_headers()

    def handle_audio_proxy(self, query):
        # 防盗链：外站把自己的页面挂上我们的音频地址会被这里挡住
        if not referer_allowed(self):
            ref = self.headers.get("Referer") or self.headers.get("Origin") or "-"
            print("[Enhancer] 拒绝盗链播放 id=%s Referer=%s"
                  % (urllib.parse.parse_qs(query or "").get("id", [""])[0], ref[:80]))
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()
            return
        prm = urllib.parse.parse_qs(query or "")
        sid = (prm.get("id", [""])[0] or "").strip()
        if not sid:
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if HEAD_ONLY.get(id(self)):
            # HEAD：只回头部（MA / ffmpeg / DLNA 渲染器都会先探测），
            # 已落盘的直接报本地文件大小，否则用 16 字节 Range 探测上游，绝不拉整曲
            lp = audio_cached(sid)
            if lp:
                size = os.path.getsize(lp)
                ct = ("audio/mp4" if lp.endswith((".m4a", ".mp4"))
                      else ("audio/flac" if lp.endswith(".flac") else "audio/mpeg"))
                return self._send_audio_head(ct, size)
            name, artist, album, dur = song_detail(sid)
            off, osz = official_url(sid)
            cand = off
            if not is_http(cand) and name:
                cand = (go_resolve(name, artist, album, dur) or {}).get("url")
            if is_http(cand):
                ct, size = probe_audio_headers(cand)
                if size:
                    return self._send_audio_head(ct, size)
            print("[Enhancer] HEAD 探测不到长度，转正常解析 id=%s" % sid)
            # 落到下面的常规流程：落盘后用本地文件长度回头部（只是慢，不会失败）

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
        meta_remember(sid, name, artist)

        # 候选顺序遵循 ADR-1：**自有 Go 音源引擎是主力**；网易云（NetEase 系统）默认不参与取音源。
        cands, seen, ai_done = [], set(), False
        # 不再把「上次解析出的直链」当候选：国内平台直链寿命以分钟计，缓存它只会换来过期 403
        # （实测日志「直链过期(403)，重新解析」）。重新解析只要 0.1–0.2 秒，永远拿新鲜的更划算。
        # 音频文件缓存（整曲落盘）在后面单独命中，那才是真正值得复用的东西。
        if name:
            res = go_resolve(name, artist, album, dur)      # ② 自有 Go 音源引擎（多平台，主力）
            fb = (res or {}).get("url")
            if is_http(fb) and fb not in seen:
                cands.append((fb, "go"))
                seen.add(fb)
            else:
                print("[Enhancer] Go 引擎无匹配 %s / %s: %s"
                      % (name, artist, (res or {}).get("attempts")))
                # 规则匹配不到：让模型在「同曲不同写法」的候选里终审（只接受同一录音）
                ai_done = True
                picked = ai_pick_source(name, artist, album, dur)
                if picked:
                    cands.append((picked["url"], "ai-pick"))
                    seen.add(picked["url"])
                    print("[Enhancer] AI 选源候选 %s / %s ← 平台 %s（%s，%s秒）"
                          % (name, artist, picked["source"],
                             picked["reason"], (picked.get("song") or {}).get("duration")))
        if ALLOW_OFFICIAL:
            # ③ 网易云直链（默认关闭）：需要临时开回时置 ALLOW_OFFICIAL=1
            off, _sz = official_url(sid)
            if off and off not in seen:
                cands.append((off, "official"))
                seen.add(off)
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
            # 直取失败（403 或只给 30 秒片段）→ 换国内出口再取一次。
            # 实测：部分平台直链与国内 IP 绑定（千千/dmhmusic：东京 403、国内 206），
            # 也有平台对海外 IP 只发试听片段 —— 这类失败是"出口不对"，不是"没音源"。
            lp_cn, why_cn = fetch_to_disk(sid, cand, dur, via_adapter=True)
            if lp_cn:
                build_entry(sid, cand, dur, src + "+cn")
                print("[Enhancer] 国内出口取流成功 %s (%s) ← %s" % (sid, name, src))
                return self.serve_audio_file(lp_cn)

            if why == "duration_rejected" and why_cn == "duration_rejected":
                rejected += 1
                print("[Enhancer] %s 来源两侧出口都只是片段，换下一个候选 %s" % (src, sid))
                continue
            print("[Enhancer] %s 来源落盘失败(直取=%s 国内=%s) %s" % (src, why, why_cn, sid))
            up_url = up_url or cand

            # 直链过期 / 被上游拒绝：立刻用 Go 引擎重新解析一次（签名链接寿命很短，重试往往就换到新链）
            if src == "go" and name:
                res2 = go_resolve(name, artist, album, dur)
                fb2 = (res2 or {}).get("url")
                if is_http(fb2) and fb2 not in seen:
                    seen.add(fb2)
                    print("[Enhancer] 直链失效，重新解析后重试 %s" % sid)
                    lp, why2 = fetch_to_disk(sid, fb2, dur)
                    if not lp:
                        lp, why2 = fetch_to_disk(sid, fb2, dur, via_adapter=True)   # 再走国内出口
                    if lp:
                        build_entry(sid, fb2, dur, "go")
                        print("[Enhancer] 重解析成功并落盘 %s (%s)" % (sid, name))
                        return self.serve_audio_file(lp)
                    print("[Enhancer] 重解析后仍失败(%s) %s" % (why2, sid))

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
                hdr = stream_headers(up_url)      # 流式代理同样要带平台 Referer
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
                    kw = (urllib.parse.parse_qs(query or "").get("keywords", [""])[0] or "").strip()
                    total = len(res["songs"])
                    # 用户只搜了一个歌名（没带歌手）时，用大模型判断「这是谁的歌」，
                    # 再把原唱捞回来放前面——平台自身的排序常把原唱压在翻唱后面甚至挤掉
                    if kw and " " not in kw and len(kw) <= 12:
                        ent = search_artist_cached(kw)
                        if ent is None:
                            threading.Thread(target=_bg_search_artist, args=(kw,), daemon=True).start()
                        elif ent.get("artist") and not _has_artist_title(res["songs"], kw, ent["artist"]):
                            extra = upstream_cloudsearch(ent["artist"] + " " + kw,
                                                         max(8, min(total, 30)))
                            # 只有补搜里**真的出现该歌手的同名原唱**才动列表，否则保持原样
                            hit = [s for s in extra if _same_title_artist(s, kw, ent["artist"])]
                            if hit:
                                res["songs"] = merge_origin_first(hit, res["songs"], total)
                                print("[Enhancer] 搜索补回原唱: %r + %s -> %d 首（列表 %d 首）"
                                      % (kw, ent["artist"], len(hit), len(res["songs"])))
                    res["songs"] = reorder_search_songs(res["songs"])
            # 列表类响应：后台预热前两首，用户点下去基本秒开
            if path not in ("/lyric", "/song/url"):
                for _sid in collect_song_ids(data, PREWARM_PER_LIST):
                    prewarm_song(_sid)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            pass
        self.send_response(code)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._wbody(body)

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
        if real == "/favorites":
            return self._json(200, {"favorites": favorites(), "count": len(favorites())})
        if real in ("/ma/play", "/ma/stream"):
            return self.handle_ma_play(p.query)
        if real == "/ma/resolve":
            return self.handle_ma_resolve(p.query)
        if real == "/ma/m3u":
            return self.handle_ma_m3u(p.query)
        if real == "/ai/continue":
            return self.handle_ai_continue(p.query)
        if real == "/ai/radio":
            qs = urllib.parse.parse_qs(p.query or "")
            q = (qs.get("q", [""])[0] or "").strip()
            try:
                want = int(qs.get("count", ["18"])[0])
            except Exception:
                want = 18
            return self.handle_ai_radio(q, min(30, max(5, want)))
        return self.proxy_upstream(real, p.query)

    def do_HEAD(self):
        """播放器（Music Assistant / ffmpeg / DLNA）探测用。
        只回头部：音频代理走轻量探测，其余接口照常算但丢弃响应体。"""
        HEAD_ONLY[id(self)] = True
        try:
            self.do_GET()          # 响应头照常输出，响应体由 _wbody 拦掉
        except Exception as e:
            print("[Enhancer] HEAD 处理失败: %s" % str(e)[:90])
        finally:
            HEAD_ONLY.pop(id(self), None)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        real = p.path[4:] if p.path.startswith("/api/") else p.path
        if real == "/client-report":
            return self.handle_client_report()
        if real == "/ai/query":
            ln = int(self.headers.get("Content-Length", 0) or 0)
            return self.handle_ai_query(p.query, self.rfile.read(ln) if ln else b"")
        if real == "/ai/continue":
            ln = int(self.headers.get("Content-Length", 0) or 0)
            return self.handle_ai_continue(p.query, self.rfile.read(ln) if ln else b"")
        if real == "/ai/ask":
            # 统一指令入口：一句话判断意图（点歌/电台/续播/控制）
            ln = int(self.headers.get("Content-Length", 0) or 0)
            return self.handle_ai_ask(self.rfile.read(ln) if ln else b"{}")
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
        elif kind == "taste":
            # 口味记忆：用户真实听了 / 跳过了什么（主播放器和 AI 面板都会上报）
            sid = str(d.get("id") or "").strip()
            act = d.get("action") or ""
            record_taste(sid, act, d.get("played") or 0, d.get("dur") or 0)
            n, a = meta_of(sid)
            print("[Enhancer] 口味记录 %s: %s%s（听了 %s 秒 / 共 %s 秒）"
                  % (act, n or sid, (" - " + a) if a else "", d.get("played"), d.get("dur")))
            return self._json(200, {"ok": True, "taste": taste_stats()})
        else:
            print("[Enhancer] 客户端回报: %s" % json.dumps(d, ensure_ascii=False)[:300])
        return self._json(200, {"ok": True, "build": BUILD})


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    print("[R-Music] Enhancer 启动 端口=%s 适配器=%s 换源=%s 网易云直链=%s"
          % (PORT, GO_ADAPTER, FALLBACK_SOURCES, "开" if ALLOW_OFFICIAL else "关（Go 引擎为主力）"))
    du, ac = disk_usage(), audio_cache_stats()
    print("[R-Music] 磁盘 %.0f%%（剩 %.1fG）缓存 %d 首 / %.0fMB"
          % (du["used_pct"], du["free_gb"], ac["files"], ac["mb"]))
    evict_audio(force=True)                      # 启动时先按水位清一次
    threading.Thread(target=recheck_worker, daemon=True).start()   # 无音源主动复核
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
