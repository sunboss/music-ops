package main

import (
	"regexp"
	"strings"

	"github.com/guohuiyuan/music-lib/model"
)

// 匹配原则：
//   - 歌名（含版本后缀）必须一致，这是防「翻唱 / 不同版本」的第一道闸
//   - 歌手允许各平台写法差异（多歌手分隔符、"feat." 等），但不能完全不相干
//   - 专辑名各平台差异极大，只作参考，不做硬性判定（硬判定会大量误杀可播放的曲子）
//   - 时长必须吻合：这是分辨「原曲 / 30 秒试听片段 / 占位音频」最可靠的依据
// 各平台时长元数据常有几秒差异（同一录音不同编码/掐头去尾），
// 容差太小会误杀正常曲目；真正防「翻唱/不同版本」靠的是歌名+版本判定，
// 防「试听片段/占位音频」靠的是落盘后的真实时长复核（差异是分钟级）。
const maxDurationDiff = 8

var artistSep = regexp.MustCompile(`[/,、;&|]|feat\.?|ft\.?|with`)

func norm(s string) string {
	return strings.ToLower(strings.Join(strings.Fields(s), " "))
}

func artistList(s string) []string {
	var out []string
	for _, p := range artistSep.Split(strings.ToLower(s), -1) {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// artistCompatible 允许分隔符、大小写、"feat." 等写法差异，也允许一方包含另一方
func artistCompatible(want, got string) bool {
	w, g := norm(want), norm(got)
	if w == g {
		return true
	}
	for _, a := range artistList(want) {
		for _, b := range artistList(got) {
			if a == b || strings.Contains(a, b) || strings.Contains(b, a) {
				return true
			}
		}
	}
	return false
}

var nonWord = regexp.MustCompile(`[^\p{Han}\p{Latin}\p{Nd}]+`)

// normLoose 去掉标点、空格、括号等一切非字母/数字/汉字字符，
// 用于容忍「」「」""（）等纯写法差异
func normLoose(s string) string {
	return nonWord.ReplaceAllString(strings.ToLower(s), "")
}

// matchLoose 放宽版：歌名去掉标点后完全一致 + 歌手兼容；
// 不判时长（同一录音各平台时长差可能超过容差），由调用方决定是否接受
func matchLoose(want, got model.Song) string {
	nw, ng := normLoose(want.Name), normLoose(got.Name)
	if nw == "" || ng == "" {
		return "title_missing"
	}
	if nw != ng {
		return "title_or_version"
	}
	if norm(want.Artist) == "" {
		return "artist_missing"
	}
	if !artistCompatible(want.Artist, got.Artist) {
		return "artist"
	}
	return ""
}

func match(want, got model.Song) string {
	nw, ng := norm(want.Name), norm(got.Name)
	if nw == "" || ng == "" {
		return "title_missing"
	}
	if nw != ng {
		return "title_or_version"
	}
	if norm(want.Artist) == "" {
		return "artist_missing"
	}
	if !artistCompatible(want.Artist, got.Artist) {
		return "artist"
	}
	if want.Duration <= 0 || got.Duration <= 0 {
		return "duration_unknown"
	}
	d := want.Duration - got.Duration
	if d < 0 {
		d = -d
	}
	if d > maxDurationDiff {
		return "duration_mismatch"
	}
	return ""
}
