package main

import (
	"testing"

	"github.com/guohuiyuan/music-lib/model"
)

// 匹配契约：
//  1. 歌名/版本不同一律拒绝（防翻唱、防 Live/Remix 混入）
//  2. 歌手完全不相干拒绝；允许分隔符、大小写、"feat." 等平台写法差异
//  3. 时长必须吻合（防 30 秒试听片段、占位音频）
//  4. 专辑名各平台写法不同，只作参考，不得作为拒绝依据
func TestStrictIdentity(t *testing.T) {
	want := model.Song{Name: "Song (Live)", Artist: "Artist", Album: "Concert", Duration: 100}

	for _, name := range []string{"Song", "Song (Remix)", "Song (Acoustic)", "Song (Cover)"} {
		got := want
		got.Name = name
		if match(want, got) == "" {
			t.Fatalf("accepted wrong version %s", name)
		}
	}

	got := want
	got.Artist = "Other"
	if match(want, got) == "" {
		t.Fatal("wrong artist accepted")
	}

	got = want
	got.Duration = 110
	if match(want, got) == "" {
		t.Fatal("wrong duration accepted")
	}

	got = want
	got.Duration = 0
	if match(want, got) == "" {
		t.Fatal("unknown duration accepted")
	}

	if match(want, want) != "" {
		t.Fatal("exact identity rejected")
	}
}

// 专辑名不参与判定：各平台写法差异极大，硬判会误杀大量可播放曲目
func TestAlbumIsNotVerdict(t *testing.T) {
	want := model.Song{Name: "晴天", Artist: "周杰伦", Album: "叶惠美", Duration: 269}
	got := want
	got.Album = "叶惠美 (Deluxe Edition)"
	if match(want, got) != "" {
		t.Fatalf("专辑写法不同被误判: %s", match(want, got))
	}
}

// 歌手写法差异应被容忍
func TestArtistVariants(t *testing.T) {
	want := model.Song{Name: "Blinding Lights", Artist: "The Weeknd", Album: "", Duration: 200}
	for _, a := range []string{"the weeknd", "The Weeknd feat. Ariana Grande", "The Weeknd/Ariana Grande"} {
		got := want
		got.Artist = a
		if match(want, got) != "" {
			t.Fatalf("歌手写法 %q 被误判: %s", a, match(want, got))
		}
	}
	got := want
	got.Artist = "Someone Else"
	if match(want, got) == "" {
		t.Fatal("完全不同的歌手被接受")
	}
}

// 时长差异必须在容差内 —— 这是挡 30 秒试听片段的关键
func TestShortClipRejected(t *testing.T) {
	want := model.Song{Name: "同花顺", Artist: "林倛玉", Album: "12蓮花", Duration: 238}
	got := want
	got.Duration = 30
	if match(want, got) == "" {
		t.Fatal("30 秒试听片段被接受")
	}
}
