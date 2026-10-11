package main
import("testing";"errors";"encoding/json";"strings";"github.com/guohuiyuan/music-lib/model")
func TestOutcome(t *testing.T){
 w:=model.Song{Name:"Song",Artist:"Artist",Duration:100};g:=w;g.ID="id";g.Source="jamendo";g.Extra=map[string]string{"opaque":"preserve"}
 r:=evaluate(w,[]model.Song{g},nil); b,_:=json.Marshal(r);if !strings.Contains(string(b),"preserve"){t.Fatal("Extra lost")};if r.Status!="matched"{t.Fatal(r.Status)}
 r=evaluate(w,nil,errors.New("provider unavailable"));if r.Status!="upstream_error" || r.Error==""{t.Fatal("error swallowed")}
 r=evaluate(w,nil,nil);if r.Status!="empty_unverified"{t.Fatal("empty misrepresented")}
 g.Name="Other";r=evaluate(w,[]model.Song{g},nil);if r.Status!="no_strict_match" || len(r.Accepted)!=0{t.Fatal("wrong result accepted")}
 g=w;g.IsInvalid=true;r=evaluate(w,[]model.Song{g},nil);if len(r.Accepted)!=0{t.Fatal("invalid accepted")}
 g=w;g.IsVIP=true;r=evaluate(w,[]model.Song{g},nil);if len(r.Accepted)!=0{t.Fatal("VIP accepted without entitlement")}
}
