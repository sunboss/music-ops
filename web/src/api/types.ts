/** 与现有网易云接口字段保持一致（ar/al/dt/privilege），避免数据层二次映射 */
export interface Artist { id: number; name: string }
export interface AlbumMeta { id: number; name: string; picUrl?: string }
export interface Song {
  id: number;
  name: string;
  ar?: Artist[];
  al?: AlbumMeta;
  dt?: number;              // 时长（毫秒）
  fee?: number;
  noCopyrightRcmd?: unknown;
  privilege?: { st?: number; pl?: number };
  /** 由本服务探测出的可用性（无完整音源时前端置灰） */
  playable?: boolean;
}
export interface Playlist {
  id: number; name: string; coverImgUrl: string; description?: string;
  trackCount?: number; playCount?: number; updateTime?: number;
  creator?: { nickname: string; avatarUrl?: string };
  tracks?: Song[];
}
export interface ArtistDetail {
  id: number; name: string; picUrl?: string; briefDesc?: string;
  albumSize?: number; musicSize?: number; mvSize?: number;
}
/** 歌手列表条目（/artist/list 返回：头像、别名、作品数） */
export interface ArtistItem {
  id: number; name: string; picUrl?: string; alias?: string[];
  albumSize?: number; musicSize?: number;
}
export interface AlbumDetail extends AlbumMeta {
  artist?: Artist; publishTime?: number; description?: string;
}
export interface SongUrlItem {
  id: number; url: string | null; size?: number; br?: number;
  /** official=官方完整 / fallback=换源 / no-source=无完整音源 */
  source?: "official" | "fallback" | "no-source" | string;
}
