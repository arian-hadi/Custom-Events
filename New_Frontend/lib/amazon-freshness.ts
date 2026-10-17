type AmazonTiming = {
  amazon_automated?: boolean;
  amazon_observed_at?: string;
  amazon_offer_expires_at?: string | null;
  amazon_content_expires_at?: string | null;
};

export function amazonFreshness(product: AmazonTiming, elapsedMs: number) {
  if (!product.amazon_automated) return { contentFresh: true, offerFresh: true };
  const observed = Date.parse(product.amazon_observed_at || '');
  const now = observed + Math.max(0, elapsedMs);
  const contentFresh = Number.isFinite(now) && Date.parse(product.amazon_content_expires_at || '') > now;
  return { contentFresh, offerFresh: contentFresh && Date.parse(product.amazon_offer_expires_at || '') > now };
}

export function nextAmazonExpiry(product: AmazonTiming, elapsedMs: number): number | null {
  const observed = Date.parse(product.amazon_observed_at || '');
  if (!product.amazon_automated || !Number.isFinite(observed)) return null;
  const remaining = [product.amazon_offer_expires_at, product.amazon_content_expires_at]
    .map(value => Date.parse(value || '') - observed - elapsedMs).filter(value => value > 0);
  return remaining.length ? Math.min(...remaining) : null;
}
