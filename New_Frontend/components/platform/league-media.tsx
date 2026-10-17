'use client';

import { useState } from 'react';
import { Play } from 'lucide-react';
import { leagueMedia } from '@/lib/league-media';

export function PlatformIcon({ platform }: { platform?: string }) {
  if (!['youtube', 'tiktok'].includes(platform || '')) return null;
  const label = platform === 'youtube' ? 'YouTube' : 'TikTok';
  return <span className="v2-platform-icon" role="img" aria-label={label} title={label}><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">{platform === 'youtube' ? <><rect x="2" y="5" width="20" height="14" rx="4" /><path d="m10 9 6 3-6 3z" fill="var(--surface, #101010)" /></> : <path d="M14 2h3c.3 2.6 1.8 4.2 4 4.5v3a9 9 0 0 1-4-1.4V16a6 6 0 1 1-6-6v3a3 3 0 1 0 3 3V2z" />}</svg></span>;
}

export function WinnerMedia({ videoUrl, title, format }: { videoUrl: string; title: string; format?: string }) {
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const media = leagueMedia(videoUrl);
  if (!media) return null;
  return <div className={`v2-winner-media${media.platform === 'tiktok' || format === 'short' ? ' portrait' : ''}`}>
    {playing ? <iframe src={media.embed} title={`${title || 'Winning edit'} · ${media.platform === 'youtube' ? 'YouTube' : 'TikTok'} player`} loading="lazy" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" /> : <button type="button" aria-label={`Play ${title || 'winning edit'}`} onClick={() => setPlaying(true)}>{media.thumbnail && !failed && <img src={media.thumbnail} alt={title || 'Winning edit preview'} loading="lazy" onError={() => setFailed(true)} />}<span className="v2-winner-play"><Play size={26} aria-hidden="true" /><span>Play edit</span><PlatformIcon platform={media.platform} /></span></button>}
  </div>;
}
