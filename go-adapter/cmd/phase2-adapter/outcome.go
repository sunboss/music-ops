package main
import "github.com/guohuiyuan/music-lib/model"
type Result struct{Status string `json:"status"`; Error string `json:"error,omitempty"`; Accepted []model.Song `json:"accepted"`; Candidates []model.Song `json:"candidates"`; Rejected []string `json:"rejected"`}
func evaluate(w model.Song,s []model.Song,e error)Result{
 r:=Result{Status:"no_strict_match",Candidates:s,Accepted:[]model.Song{},Rejected:[]string{}}
 if e!=nil{r.Status="upstream_error";r.Error=e.Error();return r}
 if len(s)==0{r.Status="empty_unverified";return r}
 for _,g:=range s{reason:=match(w,g);if g.IsInvalid{reason="invalid"};if g.IsVIP{reason="entitlement_not_verified"};if reason!=""{r.Rejected=append(r.Rejected,reason)}else{r.Accepted=append(r.Accepted,g)}}
 if len(r.Accepted)>0{r.Status="matched"};return r
}
