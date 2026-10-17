'use client';

import { useCallback, useEffect, useState } from 'react';
import type { Checkout } from './commerce';

export class ApiError extends Error {
  constructor(message: string, public status = 0, public fields: Record<string, string[]> = {}, public code = '') {
    super(message);
    this.name = 'ApiError';
  }
}

let csrfToken = '';
let csrfRequest: Promise<void> | null = null;
export function setCsrfToken(token?: string) { if (token) csrfToken = token; }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !csrfToken) {
    csrfRequest ??= api<{ csrf_token: string }>('auth/csrf/').then(data => setCsrfToken(data.csrf_token)).finally(() => { csrfRequest = null; });
    await csrfRequest;
  }
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRFToken', csrfToken);
  let response: Response;
  try {
    response = await fetch(`/api/v2/${path}`, { ...options, method, headers, credentials: 'same-origin', cache: 'no-store', signal: options.signal || AbortSignal.timeout(15000) });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('The server could not be reached. Please try again shortly.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof data?.error === 'string' ? data.error : data?.detail;
    const fields = Object.fromEntries(Object.entries(data?.errors || {}).map(([key, value]) => [key, (Array.isArray(value) ? value : [value]).map(item => typeof item === 'object' && item !== null && 'message' in item ? String(item.message) : String(item))]));
    throw new ApiError(message || (response.status === 403 ? 'This action is not permitted. Refresh the page and try again.' : 'The request could not be completed. Please try again.'), response.status, fields, data?.code || '');
  }
  if (data === null && response.status !== 204) throw new ApiError('The server returned an unexpected response. Please try again.');
  if (data?.csrf_token) setCsrfToken(data.csrf_token);
  return data as T;
}

export function mutate<T>(path: string, data: unknown = {}, method = 'POST') {
  return api<T>(path, { method, body: JSON.stringify(data) });
}

export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    if (!path) { setData(null); setLoading(false); setError(null); return; }
    const controller = new AbortController();
    setData(null); setError(null); setLoading(true);
    api<T>(path, { signal: controller.signal }).then(setData).catch(error => { if (!controller.signal.aborted) setError(error); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, version]);
  return { data, error, loading, reload };
}

export function safeUrl(value?: string | null, fallback = '#', allowMail = false): string {
  if (!value || /[\u0000-\u0020\\]/.test(value)) return fallback;
  if (/^\/(?!\/)/.test(value) || value.startsWith('#')) return value;
  try {
    const url = new URL(value);
    return ['https:', 'http:', ...(allowMail ? ['mailto:', 'tel:'] : [])].includes(url.protocol) ? value : fallback;
  } catch { return fallback; }
}

export type User = { id: number; username: string; email: string; is_verified: boolean; is_staff: boolean; role: string; profile_picture: string | null; google_linked: boolean; has_password: boolean };
export type Session = { user: User | null; csrf_token: string; google_enabled: boolean; recaptcha_site_key: string };
export type SiteLink = { label: string; url: string };
export type SiteSection = { key: string; title: string; body: string; button_text?: string; button_url?: string };
export type Site = { name: string; accent_color: string; secondary_accent_color?: string; hero_title: string; hero_subtitle: string; hero_image: string; hero_button_text: string; hero_button_url: string; logo: string; favicon: string; footer_text: string; buy_me_a_coffee_url?: string; navigation: SiteLink[]; social_links: SiteLink[]; home_sections?: SiteSection[] };
export type Category = { value?: string; label?: string; name?: string; slug?: string; count?: number } | string;
export type CatalogFacet = { value: string; label: string; count: number };
export type PageResult<T> = { results: T[]; count: number; page: number; pages: number; categories?: Category[]; total_count?: number; sort?: string; facets?: { platforms: CatalogFacet[]; currencies: CatalogFacet[]; offers: CatalogFacet[] } };
export type Product = { id: number; name: string; description: string; category: string; category_label: string; thumbnail: string; main_image: string; images: (string | { image?: string; url?: string })[]; video_url: string; original_price: string | null; current_price: string | null; currency?: string; price_available?: boolean; price_updated_at?: string | null; affiliate_disclosure?: string; content_disclosure?: string; price_disclaimer?: string; amazon_automated?: boolean; amazon_offer_expires_at?: string | null; amazon_content_expires_at?: string | null; amazon_observed_at?: string; checkout?: Checkout; discount_percentage: string | number; is_free: boolean; free_deadline: string | null; redirect_url: string; ecommerce_platform: string; is_favorite: boolean };
export type Post = { id: number; slug: string; title: string; excerpt: string; body: string; category: string; cover_image: string; published_at: string; author: string };
export type CommunityEvent = { id: number; title: string; description: string; details: string; deadline: string | null; date: string | null; deadline_passed: boolean; has_applied: boolean; fields: { id: number; name: string; field_type: string; required: boolean }[]; legacy_url?: string };
export type Application = { id: number; event: CommunityEvent; status: string; cover_letter: string; applied_date: string; updated_date: string; responses: { field_id: number; name: string; field_type: string; value: unknown }[]; legacy_url?: string; edit_url?: string; can_edit?: boolean; can_withdraw?: boolean; withdraw_api_url?: string };
export type Notification = { id: number; title?: string; message: string; is_read: boolean; created_at: string; url?: string; link?: string; type?: string };
export const dateLabel = (value?: string | null) => value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleDateString('en', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }) : '';
