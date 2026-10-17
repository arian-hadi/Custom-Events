'use client';

import { ArrowUpRight, Clapperboard, Clock3, Pin, Scissors } from 'lucide-react';
import { safeUrl, useResource } from '@/lib/api';
import { ErrorNotice } from './ui';

type FeaturedRequest = {
  id: number; title: string; description: string; details: string; image: string | null;
  icon: 'edit' | 'media'; badge: string; price_label: string; turnaround: string;
  button_label: string; placeholder_label: string; is_placeholder: boolean; purchase_url: string;
};

export function FeaturedShopRequests() {
  const { data, error, loading, reload } = useResource<{ results: FeaturedRequest[] }>('shop/featured-requests/');
  if (error) return <ErrorNotice error={error} retry={reload} />;
  if (loading) return <div className="v2-featured-requests-loading" role="status">Loading featured requests…</div>;
  if (!data?.results.length) return null;

  return <section className="v2-featured-requests" aria-label="Featured requests">
    <div className="v2-featured-requests-grid">
      {data.results.map(item => {
        const Icon = item.icon === 'media' ? Clapperboard : Scissors;
        const image = safeUrl(item.image, '');
        const purchaseUrl = item.is_placeholder ? '' : safeUrl(item.purchase_url, '');
        return <article key={item.id} className="v2-request-card">
          {image && <img className="v2-request-image" src={image} alt="" loading="lazy" />}
          <div className="v2-request-content">
            <div className="v2-request-topline"><span className="v2-request-icon"><Icon size={24} aria-hidden="true" /></span>{item.badge && <span className="v2-request-badge"><Pin size={12} aria-hidden="true" />{item.badge}</span>}</div>
            <h2>{item.title}</h2>
            <p className="v2-request-description">{item.description}</p>
            <div className="v2-request-meta">{item.price_label && <span>{item.price_label}</span>}{item.turnaround && <span><Clock3 size={14} aria-hidden="true" />{item.turnaround}</span>}</div>
            {item.details && <details className="v2-request-details"><summary>What’s included</summary><p>{item.details}</p></details>}
            <div className="v2-request-action">{purchaseUrl
              ? <><a className="v2-button" href={purchaseUrl} target="_blank" rel="noopener noreferrer">{item.button_label}<ArrowUpRight size={17} aria-hidden="true" /></a><span className="v2-request-payment-note">Checkout on Buy Me a Coffee</span></>
              : <button className="v2-button secondary" type="button" disabled>{item.placeholder_label}</button>}
            </div>
          </div>
        </article>;
      })}
    </div>
  </section>;
}
