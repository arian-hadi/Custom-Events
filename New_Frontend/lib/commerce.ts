export type Checkout = {
  configured: boolean; enabled: boolean; amount_minor?: number;
  currency?: string; display_amount?: string; fulfillment_kind?: string; fulfillment_note?: string;
};

export function currencyLabel(amount: string | null | undefined, currency = 'USD'): string {
  if (amount == null || amount.trim() === '' || !Number.isFinite(Number(amount))) return 'Price unavailable';
  try { return new Intl.NumberFormat('en', { style: 'currency', currency: currency.toUpperCase() }).format(Number(amount)); }
  catch { return 'Price unavailable'; }
}

// Checkout currently uses Stripe's hosted domain, never a browser-supplied URL.
export function stripeCheckoutUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'checkout.stripe.com' && !url.port && !url.username && !url.password
      ? url.href : null;
  } catch { return null; }
}

export function paymentStatusLabel(status: string): string {
  return ({ pending: 'Waiting for payment confirmation', creating: 'Preparing checkout', open: 'Awaiting payment', processing: 'Payment processing', paid: 'Payment confirmed', failed: 'Payment failed', review_required: 'Our team is reviewing this payment', expired: 'Checkout expired', cancelled: 'Checkout cancelled' } as Record<string, string>)[status] || 'Payment confirmation pending';
}
