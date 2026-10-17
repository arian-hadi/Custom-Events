/** Derive only supported provider player URLs; never render provider HTML. */
export function leagueMedia(value: string) {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.port) return null;
    let id = '';
    if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'].includes(url.hostname)) {
      if (url.hostname.endsWith('youtu.be')) id = url.pathname.slice(1);
      else if (url.pathname === '/watch' && url.searchParams.getAll('v').length === 1) id = url.searchParams.get('v') || '';
      else id = url.pathname.match(/^\/(?:shorts|embed|live)\/([\w-]+)\/?$/)?.[1] || '';
      if (!/^[\w-]{11}$/.test(id)) return null;
      return { platform: 'youtube', embed: `https://www.youtube-nocookie.com/embed/${id}?rel=0`, thumbnail: `https://i.ytimg.com/vi/${id}/hqdefault.jpg` };
    }
    if (['www.tiktok.com', 'tiktok.com', 'm.tiktok.com'].includes(url.hostname)) {
      id = url.pathname.match(/^\/@[\w.-]+\/video\/(\d{10,30})\/?$/)?.[1] || '';
      if (id) return { platform: 'tiktok', embed: `https://www.tiktok.com/player/v1/${id}?autoplay=0`, thumbnail: '' };
    }
  } catch { /* Unsupported or missing links retain the ordinary fallback. */ }
  return null;
}
