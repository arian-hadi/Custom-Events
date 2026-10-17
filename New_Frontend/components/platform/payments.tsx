'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiError, api, dateLabel, mutate, useResource, type Product } from '@/lib/api';
import { currencyLabel, paymentStatusLabel, stripeCheckoutUrl } from '@/lib/commerce';
import { RequireAccount } from './auth';
import { AccountNav } from './account-nav';
import { useSite } from './site-shell';
import { Empty, ErrorNotice, Loading, Notice, PageHeading } from './ui';

type Order = {
  id: string; product_id: number; product_name: string; display_amount: string; currency: string;
  status: string; fulfillment_status: string; fulfillment_note: string; created_at: string; paid_at: string | null;
};

export function CheckoutButton({ product }: { product: Product }) {
  const { user } = useSite();
  const requestKey = useRef('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [expired, setExpired] = useState(false);
  const storageKey = `checkout-request:${user?.id}:${product.id}`;
  function clearRequest() {
    requestKey.current = '';
    try { sessionStorage.removeItem(storageKey); } catch { /* Memory-only fallback. */ }
  }
  async function checkout() {
    if (!user) { window.location.assign(`/login?next=${encodeURIComponent(`/product/${product.id}`)}`); return; }
    setBusy(true); setError(null);
    try {
      // Keep uncertain requests across reloads. Never silently create a new order.
      if (!requestKey.current) {
        try { const saved = sessionStorage.getItem(storageKey); if (saved && /^[0-9a-f-]{36}$/i.test(saved)) requestKey.current = saved; } catch { /* Storage may be disabled. */ }
      }
      requestKey.current ||= crypto.randomUUID();
      try { sessionStorage.setItem(storageKey, requestKey.current); } catch { /* Same-mount retries still reuse the key. */ }
      const result = await mutate<{ order: Order; checkout_url: string | null }>('payments/checkout/', { product_id: product.id, idempotency_key: requestKey.current });
      if (!result.checkout_url || result.order.status === 'paid') {
        if (['paid', 'failed', 'expired', 'cancelled'].includes(result.order.status)) clearRequest();
        window.location.assign(`/account/orders/${result.order.id}`); return;
      }
      const url = stripeCheckoutUrl(result.checkout_url);
      if (!url) throw new Error('Checkout could not be opened. Please try again or contact us.');
      window.location.assign(url);
    } catch (error) { setError(error as Error); setExpired(error instanceof ApiError && error.code === 'expired_request'); setBusy(false); }
  }
  return <div><button className="v2-button" onClick={checkout} disabled={busy || expired || !product.checkout?.enabled}>{busy ? 'Opening secure checkout…' : product.checkout?.enabled ? 'Buy with Stripe' : 'Checkout unavailable'}</button><ErrorNotice error={error} />{expired && <p><a href="/account/orders">Check your previous orders</a>, then <button className="v2-text-button" onClick={() => { clearRequest(); setExpired(false); setError(null); }}>start a new checkout</button> if needed.</p>}</div>;
}

export function OrdersPage() {
  return <div className="v2-container v2-page"><AccountNav active="orders" /><PageHeading title="Your orders" eyebrow="Your account"><p>Track payments and delivery updates for purchases made here.</p></PageHeading><RequireAccount><Orders /></RequireAccount></div>;
}

function Orders() {
  const result = useResource<{ orders: Order[] }>('payments/orders/');
  return <><ErrorNotice error={result.error} retry={result.reload} />{result.loading && <Loading />}{result.data && (result.data.orders.length ? <div className="v2-stack">{result.data.orders.map(order => <article className="v2-panel" key={order.id}><h2><a href={`/account/orders/${order.id}`}>{order.product_name}</a></h2><p>{currencyLabel(order.display_amount, order.currency)} · {dateLabel(order.created_at)}</p><p>{paymentStatusLabel(order.status)}</p><a className="v2-arrow-link" href={`/account/orders/${order.id}`}>View order →</a></article>)}</div> : <Empty title="No orders yet">Purchases from Amazon and other external stores are managed by those stores.</Empty>)}</>;
}

export function OrderPage({ id, returnedFromCheckout = false }: { id: string; returnedFromCheckout?: boolean }) {
  return <div className="v2-container v2-page"><AccountNav active="orders" /><a className="v2-back-link" href="/account/orders">← Your orders</a><PageHeading title="Order details" /><RequireAccount><OrderDetails id={id} returnedFromCheckout={returnedFromCheckout} /></RequireAccount></div>;
}

function OrderDetails({ id, returnedFromCheckout }: { id: string; returnedFromCheckout: boolean }) {
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setOrder(null); setError(null);
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await api<{ order: Order }>(`payments/orders/${encodeURIComponent(id)}/`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setOrder(result.order); setError(null);
        if (!['paid', 'failed', 'expired', 'cancelled', 'review_required'].includes(result.order.status) && ++attempts < 24) timer = setTimeout(load, 5000);
      } catch (error) { if (!controller.signal.aborted) setError(error as Error); }
    }
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [id, refresh]);
  return <><ErrorNotice error={error} retry={() => setRefresh(value => value + 1)} />{!order && !error && <Loading label="Checking your order…" />}{order && <section className="v2-panel"><h2>{order.product_name}</h2><p>{currencyLabel(order.display_amount, order.currency)}</p><Notice>{paymentStatusLabel(order.status)}</Notice>{returnedFromCheckout && order.status !== 'paid' && <p>Your payment status will update when confirmation arrives. Returning from checkout does not confirm a payment.</p>}<p className="v2-small v2-muted">Order {order.id} · {dateLabel(order.created_at)}</p>{order.status === 'paid' && <p>Fulfillment: {order.fulfillment_status.replaceAll('_', ' ')}.</p>}{order.fulfillment_note && <p>{order.fulfillment_note}</p>}<div className="v2-actions"><button className="v2-button secondary" onClick={() => setRefresh(value => value + 1)}>Refresh status</button><a href="/contact" className="v2-arrow-link">Contact us about this order →</a></div></section>}</>;
}
