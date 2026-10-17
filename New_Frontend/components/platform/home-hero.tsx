'use client';

import { useEffect, useRef, useState } from 'react';
import { safeUrl, type Site } from '@/lib/api';

export function HomeHero({ site, loading }: { site: Site; loading: boolean }) {
  const image = useRef<HTMLImageElement>(null);
  const [imageResult, setImageResult] = useState<{ src: string; failed: boolean } | null>(null);
  // A neutral placeholder occupies the artwork's space until admin settings arrive.
  // Never request demo artwork while the real URL is still unknown.
  const source = loading ? '' : safeUrl(site.hero_image, '');
  const resolved = imageResult?.src === source;
  const failed = resolved && imageResult.failed;
  const artworkReady = !loading && (!source || resolved);

  useEffect(() => {
    // Cached images can finish before React attaches the load handler.
    const node = image.current;
    if (source && node?.complete) setImageResult({ src: source, failed: !node.naturalWidth });
  }, [source]);

  return <section className="v2-home-intro" data-content-ready={!loading} data-art-ready={artworkReady} aria-busy={loading}>
    <div className="v2-container v2-intro-grid">
      <div className="v2-intro-copy">
        {loading ? <><span className="v2-visually-hidden" role="status">Loading homepage…</span><div className="v2-hero-copy-placeholder" aria-hidden="true"><span /><span /><span /><span /></div></> : <>
          <span className="v2-eyebrow">Welcome to {site.name}</span>
          <h1 className="v2-hero-title">{site.hero_title}</h1>
          <p className="v2-hero-copy">{site.hero_subtitle}</p>
          <div className="v2-hero-presence" aria-label="Our community">
            <a href="/editing-hub">Active editors<small>A community of creators</small></a>
            <a href="/editing-hub#league-standings">Weekly challenges<small>Make your next great edit</small></a>
          </div>
          <a href={safeUrl(site.hero_button_url, '/editing-hub')} className="v2-button hero-button">{site.hero_button_text || 'Explore'} <span aria-hidden="true">↗</span></a>
        </>}
      </div>
      <div className="v2-hero-visual" aria-hidden="true">
        <div className="v2-hero-image-mask">
          {source && !failed ? <img key={source} ref={image} src={source} fetchPriority="high" width={600} height={600} alt=""
            onLoad={() => setImageResult({ src: source, failed: false })}
            onError={() => setImageResult({ src: source, failed: true })} />
            : !loading && <span className="v2-hero-art-placeholder">TF</span>}
        </div>
      </div>
    </div>
  </section>;
}
