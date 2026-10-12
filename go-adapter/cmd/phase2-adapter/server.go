package main

// 隔离实验用适配器（不上生产）：
//   /resolve      严格匹配搜索，逐来源返回状态与错误，保留歌曲完整元数据
//   /resolve-url  仅在严格匹配通过后返回真实音频直链
// 设计原则：绝不吞掉来源错误、绝不伪造 duration/size/bitrate、绝不接受版本不符的候选。

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/guohuiyuan/go-music-dl/core"
	"github.com/guohuiyuan/music-lib/model"
)

type sourceOutcome struct {
	Source     string       `json:"source"`
	Status     string       `json:"status"` // matched / no_strict_match / empty_unverified / unsupported_source / upstream_error
	Error      string       `json:"error,omitempty"`
	Candidate  *model.Song  `json:"candidate,omitempty"`
	Rejected   []string     `json:"rejected,omitempty"`
	Candidates []model.Song `json:"candidates,omitempty"`
}

type resolveResponse struct {
	Want     model.Song      `json:"want"`
	Keyword  string          `json:"keyword"`
	Status   string          `json:"status"` // matched / no_match / partial_error / all_error
	Outcomes []sourceOutcome `json:"outcomes"`
}

func parseWant(r *http.Request) model.Song {
	d, _ := strconv.Atoi(r.URL.Query().Get("duration"))
	return model.Song{
		Name:     strings.TrimSpace(r.URL.Query().Get("name")),
		Artist:   strings.TrimSpace(r.URL.Query().Get("artist")),
		Album:    strings.TrimSpace(r.URL.Query().Get("album")),
		Duration: d,
	}
}

func splitSources(v string) []string {
	if strings.TrimSpace(v) == "" {
		v = "jamendo,netease"
	}
	var out []string
	for _, s := range strings.Split(v, ",") {
		if s = strings.TrimSpace(s); s != "" {
			out = append(out, s)
		}
	}
	return out
}

func handleResolve(w http.ResponseWriter, r *http.Request) {
	want := parseWant(r)
	resp := resolveResponse{Want: want}
	if want.Name == "" {
		writeJSON(w, 400, map[string]string{"error": "name is required"})
		return
	}
	kw := strings.TrimSpace(want.Artist + " " + want.Name)
	resp.Keyword = kw

	matched, errored := 0, 0
	for _, src := range splitSources(r.URL.Query().Get("sources")) {
		out := sourceOutcome{Source: src}
		fn := core.GetSearchFunc(src)
		if fn == nil {
			// 明确报告不支持，而不是当作“无结果”
			out.Status, out.Error = "unsupported_source", "source not supported by upstream"
		} else {
			songs, err := fn(kw)
			if err != nil {
				out.Status, out.Error = "upstream_error", err.Error()
			} else if len(songs) == 0 {
				out.Status = "empty_unverified"
			} else {
				out.Candidates = songs
				out.Status = "no_strict_match"
				for i := range songs {
					g := songs[i]
					reason := match(want, g)
					if g.IsInvalid {
						reason = "invalid"
					} else if g.IsVIP && reason == "" {
						reason = "entitlement_not_verified"
					}
					if reason == "" {
						c := g
						out.Candidate = &c
						out.Status = "matched"
						break
					}
					out.Rejected = append(out.Rejected, fmt.Sprintf("%s/%s:%s", g.Name, g.Artist, reason))
				}
			}
		}
		if out.Status == "matched" {
			matched++
		}
		if out.Status == "upstream_error" {
			errored++
		}
		resp.Outcomes = append(resp.Outcomes, out)
	}
	switch {
	case matched > 0 && errored == 0:
		resp.Status = "matched"
	case matched > 0:
		resp.Status = "matched" // 有匹配就算匹配，但 Outcomes 里保留了错误明细
	case errored == len(resp.Outcomes):
		resp.Status = "all_error"
	case errored > 0:
		resp.Status = "partial_error"
	default:
		resp.Status = "no_match"
	}
	writeJSON(w, 200, resp)
}

func handleResolveURL(w http.ResponseWriter, r *http.Request) {
	want := parseWant(r)
	loose := r.URL.Query().Get("loose") == "1"
	src := strings.TrimSpace(r.URL.Query().Get("source"))
	if want.Name == "" || src == "" {
		writeJSON(w, 400, map[string]string{"error": "name and source are required"})
		return
	}
	search := core.GetSearchFunc(src)
	dl := core.GetDownloadFunc(src)
	if search == nil || dl == nil {
		writeJSON(w, 400, map[string]string{"error": "unsupported source: " + src})
		return
	}
	songs, err := search(strings.TrimSpace(want.Artist + " " + want.Name))
	if err != nil {
		writeJSON(w, 502, map[string]string{"error": "upstream search failed: " + err.Error()})
		return
	}
	var picked *model.Song
	for i := range songs {
		g := songs[i]
		if g.IsInvalid || g.IsVIP {
			continue
		}
		if (loose && matchLoose(want, g) == "") || (!loose && match(want, g) == "") {
			picked = &g
			break
		}
	}
	if picked == nil {
		writeJSON(w, 404, map[string]string{"error": "no strict match", "searched": kwOf(want),
			"loose": strconv.FormatBool(loose)})
		return
	}
	url, err := dl(picked)
	if err != nil {
		writeJSON(w, 502, map[string]string{"error": "download url failed: " + err.Error()})
		return
	}
	if u := strings.TrimSpace(url); !strings.HasPrefix(u, "http://") && !strings.HasPrefix(u, "https://") {
		writeJSON(w, 502, map[string]string{"error": "upstream returned a non-url value: " +
			truncateStr(u, 40)})
		return
	}
	// 只回传上游真实返回的字段；不推断、不编造 size/bitrate
	writeJSON(w, 200, map[string]any{
		"song": picked, "url": url, "loose": loose,
		"size_reported": picked.Size, "bitrate_reported": picked.Bitrate,
		"note": "size/bitrate 为上游上报值，未经验证；请以实际下载与解码结果为准",
	})
}

func kwOf(s model.Song) string { return strings.TrimSpace(s.Artist + " " + s.Name) }

// queryVariants 搜索词变体：先「歌手 歌名」，再单用歌名
func queryVariants(want model.Song) []string {
	var out []string
	if v := kwOf(want); v != "" {
		out = append(out, v)
	}
	n := strings.TrimSpace(want.Name)
	if n != "" && n != kwOf(want) {
		out = append(out, n)
	}
	return out
}

// hasMatch 候选里是否已有严格匹配
func hasMatch(want model.Song, songs []model.Song) bool {
	for i := range songs {
		if songs[i].IsInvalid || songs[i].IsVIP {
			continue
		}
		if match(want, songs[i]) == "" {
			return true
		}
	}
	return false
}

func truncateStr(s string, n int) string {
	if len(s) > n {
		return s[:n] + "..."
	}
	return s
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}

// handleResolveBest 按来源优先级找第一个“严格匹配通过”的结果，并取真实直链。
// 无匹配时返回 404，明确表示“没有可用音源”，绝不退而求其次播放别的版本。
func handleResolveBest(w http.ResponseWriter, r *http.Request) {
	want := parseWant(r)
	if want.Name == "" {
		writeJSON(w, 400, map[string]string{"error": "name is required"})
		return
	}
	type attempt struct {
		Source string `json:"source"`
		Status string `json:"status"`
		Error  string `json:"error,omitempty"`
	}
	attempts := []attempt{}
	for _, src := range splitSources(r.URL.Query().Get("sources")) {
		search := core.GetSearchFunc(src)
		dl := core.GetDownloadFunc(src)
		if search == nil || dl == nil {
			attempts = append(attempts, attempt{Source: src, Status: "unsupported_source"})
			continue
		}
		// 各平台对「歌手 歌名」的召回差异很大：只用一种写法会漏掉大量可播放曲目
		// （实测「陈奕迅 十年」只回 3 条，去掉歌手搜「十年」回 7 条）。
		// 这里合并多个搜索词的候选，只要其中一条严格匹配即可。
		songs := []model.Song{}
		seen := map[string]bool{}
		var searchErr error
		for _, q := range queryVariants(want) {
			got, err := search(q)
			if err != nil {
				searchErr = err
				continue
			}
			for _, s := range got {
				key := fmt.Sprintf("%s\x1f%s\x1f%d", s.Name, s.Artist, s.Duration)
				if !seen[key] {
					seen[key] = true
					songs = append(songs, s)
				}
			}
			if hasMatch(want, songs) {
				break // 已经能匹配上，不必再换搜索词
			}
		}
		if searchErr != nil && len(songs) == 0 {
			attempts = append(attempts, attempt{Source: src, Status: "upstream_error", Error: searchErr.Error()})
			continue
		}
		if len(songs) == 0 {
			attempts = append(attempts, attempt{Source: src, Status: "empty_unverified"})
			continue
		}
		var picked *model.Song
		rejected := 0
		// prefer=speed：在全部严格匹配候选里挑体积最小的（约 320k 或更低），
		// 而不是第一个——省流量、快起播；默认 lossless 保持原行为（第一个匹配，
		// 上游 kuwo 本身从 2000kflac 往下试，天然最高音质优先）。
		preferSpeed := r.URL.Query().Get("prefer") == "speed"
		var bestSize int64
		for i := range songs {
			g := songs[i]
			if g.IsInvalid || g.IsVIP {
				rejected++
				continue
			}
			if match(want, g) == "" {
				if preferSpeed {
					if picked == nil || (g.Size > 0 && (bestSize <= 0 || g.Size < bestSize)) {
						picked = &g
						bestSize = g.Size
					}
					continue
				}
				picked = &g
				break
			}
			rejected++
		}
		if picked == nil {
			// 二次匹配：严格匹配（含时长容差）全部被拒时，对非 VIP/非 invalid
			// 候选再跑一轮 matchLoose（歌名去标点全等 + 歌手兼容，不判时长——
			// 同一录音各平台时长常差 10-30s）。仍不播放翻唱/Live/变速版：
			// 歌名与歌手必须原样等价。
			for i := range songs {
				g := songs[i]
				if g.IsInvalid || g.IsVIP {
					continue
				}
				if matchLoose(want, g) == "" {
					picked = &g
					break
				}
			}
			if picked != nil {
				attempts = append(attempts, attempt{Source: src, Status: "loose_match(严格被拒后二次匹配,未判时长)"})
			}
		}
		if picked == nil {
			attempts = append(attempts, attempt{Source: src, Status: fmt.Sprintf("no_strict_match(%d候选被拒)", rejected)})
			continue
		}
		url, err := dl(picked)
		if err != nil {
			attempts = append(attempts, attempt{Source: src, Status: "download_url_failed", Error: err.Error()})
			continue
		}
		// 上游在取不到真实直链时会返回空串甚至字符串 "None"；不是 http(s) 一律拒绝
		// （此前的换源缺陷正是把这类无效值当成可播放链接回填给播放器）
		trimmed := strings.TrimSpace(url)
		if !strings.HasPrefix(trimmed, "http://") && !strings.HasPrefix(trimmed, "https://") {
			attempts = append(attempts, attempt{Source: src, Status: "invalid_url_from_source",
				Error: fmt.Sprintf("上游返回非链接内容(%d 字节): %s", len(trimmed), truncateStr(trimmed, 40))})
			continue
		}
		writeJSON(w, 200, map[string]any{
			"status": "matched", "source": src, "song": picked, "url": url, "attempts": attempts,
			"note": "size/bitrate 请以实际下载字节为准，本接口不推断",
		})
		return
	}
	writeJSON(w, 404, map[string]any{
		"status": "no_available_source", "attempts": attempts, "want": want,
		"note": "严格匹配未通过，前端应提示无可用音源，而不是播放其他版本",
	})
}

// 已配置 Cookie 的来源名（只保留名字，绝不记录取值）
var cookieSources []string

// loadCookies 从 JSON 文件按来源注入 Cookie，格式: {"migu":"...", "qq":"..."}
// 用途：让取链使用使用者自己的会员权益，而不是绕过对方平台的付费限制。
func loadCookies(path string) {
	cookieSources = nil
	data, err := os.ReadFile(path)
	if err != nil {
		log.Printf("未加载 Cookie 文件 %s（来源将按匿名访问处理）", path)
		return
	}
	var m map[string]string
	if err := json.Unmarshal(data, &m); err != nil {
		log.Printf("Cookie 文件解析失败 %s: %v", path, err)
		return
	}
	core.CM.SetAll(m)
	for k := range m {
		cookieSources = append(cookieSources, k)
	}
	sort.Strings(cookieSources)
	log.Printf("已注入 %d 个来源的 Cookie: %v", len(cookieSources), cookieSources)
}

// handleFetch 通过本进程的出口（容器已配好国内代理）代抓音频。
// 为什么音频也必须走这里：国内平台对海外 IP 可能只返回 30 秒试听片段，
// 直连抓取即使时长校验能看出问题，也拿不到完整音频。
// 传 url= 为要抓的地址；Range 头原样透传，返回上游状态码与关键响应头。
func handleFetch(w http.ResponseWriter, r *http.Request) {
	raw := strings.TrimSpace(r.URL.Query().Get("url"))
	if !strings.HasPrefix(raw, "http://") && !strings.HasPrefix(raw, "https://") {
		writeJSON(w, 400, map[string]string{"error": "url must be http(s)"})
		return
	}
	req, err := http.NewRequest("GET", raw, nil)
	if err != nil {
		writeJSON(w, 400, map[string]string{"error": err.Error()})
		return
	}
	req.Header.Set("User-Agent", browserUAHeader)
	if rg := r.Header.Get("Range"); rg != "" {
		req.Header.Set("Range", rg)
	}
	client := &http.Client{Timeout: 10 * time.Minute} // 走代理抓整曲，给足时间
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("fetch failed %s: %v", truncateStr(raw, 60), err)
		writeJSON(w, 502, map[string]string{"error": err.Error()})
		return
	}
	defer resp.Body.Close()
	for _, k := range []string{"Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"} {
		if v := resp.Header.Get(k); v != "" {
			w.Header().Set(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	if _, err := io.Copy(w, resp.Body); err != nil {
		log.Printf("fetch stream interrupted: %v", err)
	}
}

const browserUAHeader = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
	"(KHTML, like Gecko) Chrome/131.0 Safari/537.36"

func main() {
	addr := flag.String("addr", "127.0.0.1:0", "loopback listen address")
	cookies := flag.String("cookies", "/data/cookies.json", "按来源提供 Cookie 的 JSON 文件路径")
	flag.Parse()
	loadCookies(*cookies)

	mux := http.NewServeMux()
	mux.HandleFunc("/resolve", handleResolve)
	mux.HandleFunc("/resolve-url", handleResolveURL)
	mux.HandleFunc("/resolve-best", handleResolveBest)
	mux.HandleFunc("/fetch", handleFetch)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"app": "phase2-adapter", "status": "ok",
			"time": time.Now().Format(time.RFC3339), "cookie_sources": cookieSources})
	})

	srv := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	ln, err := net.Listen("tcp", srv.Addr)
	if err != nil {
		log.Fatalf("listen failed: %v", err)
	}
	// 打印实际端口，便于探针读取
	fmt.Printf("ADAPTER_READY http://%s\n", ln.Addr().String())
	log.SetFlags(0)
	log.Printf("phase2-adapter listening on %s", ln.Addr().String())
	if err := srv.Serve(ln); err != nil && err != http.ErrServerClosed {
		log.Fatalf("serve failed: %v", err)
	}
}
