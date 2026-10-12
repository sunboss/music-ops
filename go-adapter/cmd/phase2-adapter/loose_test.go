package main

import (
	"testing"

	"github.com/guohuiyuan/music-lib/model"
)

// 二次匹配：时长差超容差但歌名/歌手等价的候选应被 matchLoose 救回；
// 翻唱（歌手不同）与改词版（歌名不同）不应被救回。
func TestLooseMatchRescuesDurationMismatchOnly(t *testing.T) {
	want := model.Song{Name: "不要说话", Artist: "陈奕迅", Duration: 253}
	cases := []struct {
		name    string
		got     model.Song
		wantOK  bool
	}{
		{"时长差20s_同曲", model.Song{Name: "不要说话", Artist: "陈奕迅", Duration: 273}, true},
		{"标点差异", model.Song{Name: "不要说话 (Live)", Artist: "陈奕迅", Duration: 253}, false}, // Live 版歌名含括号内容则去标点后仍等价?——Live 在歌名里应被拒
		{"翻唱歌手不同", model.Song{Name: "不要说话", Artist: "某某翻唱", Duration: 253}, false},
		{"歌名不同", model.Song{Name: "不要说话(DJ版)", Artist: "陈奕迅", Duration: 253}, false},
	}
	for _, c := range cases {
		err := matchLoose(want, c.got)
		ok := err == ""
		if ok != c.wantOK {
			t.Errorf("%s: matchLoose=%q wantOK=%v", c.name, err, c.wantOK)
		}
	}
}
