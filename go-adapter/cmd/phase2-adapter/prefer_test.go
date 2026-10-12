package main

import (
	"testing"

	"github.com/guohuiyuan/music-lib/model"
)

func TestPreferSpeedPicksSmallest(t *testing.T) {
	cands := []model.Song{
		{Name: "Test Song", Artist: "A", Duration: 200, Size: 30_000_000},
		{Name: "Test Song", Artist: "A", Duration: 200, Size: 4_000_000},
		{Name: "Test Song", Artist: "A", Duration: 200, Size: 12_000_000},
	}
	want := model.Song{Name: "Test Song", Artist: "A", Duration: 200}
	// speed：应挑 4MB 那个；lossless 语义（第一个匹配）挑 30MB
	smallest := int64(0)
	for i := range cands {
		if match(want, cands[i]) != "" {
			t.Fatal("match should pass")
		}
		if smallest == 0 || cands[i].Size < smallest {
			smallest = cands[i].Size
		}
	}
	if smallest != 4_000_000 {
		t.Fatalf("smallest=%d", smallest)
	}
}
