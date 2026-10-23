'use client';

import { useState } from 'react';
import { ArrowUpRight, Clapperboard, Clock3, Pin, Scissors } from 'lucide-react';
import { safeUrl } from '@/lib/api';
import type { FeaturedRequest } from '@/lib/shop-requests';

/** A pinned catalog item; uses the same media and content layout as products. */
export function FeaturedRequestCard({ item }: { item: FeaturedRequest }) {
  const [failed, setFailed] = useState('');
  const Icon = item.icon === 'media' ? Clapperboard : Scissors;
  const image = safeUrl(item.image, '');
  const purchaseUrl = item.is_placeholder ? '' : safeUrl(item.purchase_url, '');
  return <article className="v2-shop-product v2-shop-request">
    <div className="v2-shop-product-media">
      <div className="v2-shop-product-image v2-shop-request-image">{image && image !== failed
        ? <img src={image} alt="" loading="lazy" onError={() => setFailed(image)} />
        : <Icon size={60} strokeWidth={1.2} aria-hidden="true" />}</div>
      <span className="v2-shop-product-label v2-shop-request-pin"><Pin size={12} aria-hidden="true" />Pinned{item.badge && item.badge.toLowerCase() !== 'pinned' ? ` · ${item.badge}` : ''}</span>
    </div>
    <div className="v2-shop-product-info">
      <span className="v2-shop-category">Creative requests</span>
      <h3>{item.title}</h3>
      {item.price_label && <span className="v2-price">{item.price_label}</span>}
      <p className="v2-shop-request-description">{item.description}</p>
      {item.turnaround && <span className="v2-shop-request-turnaround"><Clock3 size={14} aria-hidden="true" />{item.turnaround}</span>}
      {item.details && <details className="v2-request-details"><summary>What’s included</summary><p>{item.details}</p></details>}
      <div className="v2-shop-request-action">{purchaseUrl
        ? <><a className="v2-button compact" href={purchaseUrl} target="_blank" rel="noopener noreferrer">{item.button_label}<ArrowUpRight size={15} aria-hidden="true" /></a><span className="v2-shop-product-source">Checkout on Buy Me a Coffee</span></>
        : <button className="v2-button secondary compact" type="button" disabled>{item.placeholder_label}</button>}
      </div>
    </div>
  </article>;
}
