'use client';

import { useState } from 'react';
import { safeUrl, type Site } from '@/lib/api';

/** Use the same admin-managed branding as the site, including while settings load. */
export function AuthArt({ site, loading }: { site: Site | null; loading: boolean }) {
  const [failed, setFailed] = useState('');
  const image = loading ? '' : safeUrl(site?.logo, '') || safeUrl(site?.hero_image, '');
  return <div className="v2-auth-art" aria-hidden="true">
    <div className="v2-orbit" />
    <div className="v2-auth-brand-image">{image && image !== failed
      ? <img src={image} alt="" onError={() => setFailed(image)} />
      : <span className="v2-auth-brand-placeholder">{loading ? '' : 'TF'}</span>}</div>
    <p>Create. Connect.<br />Make it yours.</p>
  </div>;
}
