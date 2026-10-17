'use client';

import { useEffect, useState } from 'react';
import type { Product } from './api';
import { amazonFreshness, nextAmazonExpiry } from './amazon-freshness';

export function useAmazonProduct(product: Product): Product | null {
  const [clock, setClock] = useState({ product, elapsed: 0 });
  const elapsed = clock.product === product ? clock.elapsed : 0;
  useEffect(() => {
    if (!product.amazon_automated) return;
    const monotonicStart = performance.now();
    const wallStart = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const update = () => {
      if (timer) clearTimeout(timer);
      // Relative to the backend observation, with wall time also accounting for sleep.
      const passed = Math.max(performance.now() - monotonicStart, Date.now() - wallStart, 0);
      setClock({ product, elapsed: passed });
      const next = nextAmazonExpiry(product, passed);
      if (next !== null) timer = setTimeout(update, Math.min(next + 1, 2147483647));
    };
    update();
    document.addEventListener('visibilitychange', update);
    window.addEventListener('focus', update);
    return () => { if (timer) clearTimeout(timer); document.removeEventListener('visibilitychange', update); window.removeEventListener('focus', update); };
  }, [product]);
  const freshness = amazonFreshness(product, elapsed);
  if (!freshness.contentFresh) return null;
  if (!freshness.offerFresh) return { ...product, current_price: null, original_price: null, price_available: false, price_updated_at: null };
  return product;
}
