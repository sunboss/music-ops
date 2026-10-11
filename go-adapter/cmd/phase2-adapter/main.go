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
const maxDurationDiff = 3

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
