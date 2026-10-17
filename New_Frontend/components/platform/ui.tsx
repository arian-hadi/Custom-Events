'use client';

import { createElement, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ApiError, safeUrl } from '@/lib/api';

export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`v2-notice${error ? ' v2-error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>;
}
export function ErrorNotice({ error, retry }: { error: Error | null; retry?: () => void }) {
  if (!error) return null;
  return <Notice error><p>{error.message}</p>{error instanceof ApiError && Object.entries(error.fields).map(([field, messages]) => <p key={field}><strong>{field.replaceAll('_', ' ')}: </strong>{Array.isArray(messages) ? messages.join(' ') : String(messages)}</p>)}{retry && <button className="v2-button secondary compact" onClick={retry}>Try again</button>}</Notice>;
}
export function Loading({ label = 'Loading…' }: { label?: string }) { return <div className="v2-loading" role="status"><span className="v2-spinner" />{label}</div>; }
export function Empty({ title, children }: { title: string; children?: ReactNode }) { return <div className="v2-empty"><span aria-hidden="true">✦</span><h3>{title}</h3>{children && <p>{children}</p>}</div>; }
export function PageHeading({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) { return <header className="v2-page-heading">{eyebrow && <span className="v2-eyebrow">{eyebrow}</span>}<h1>{title}</h1>{children && <div className="v2-intro">{children}</div>}</header>; }
export function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="v2-field"><span>{label}</span>{children}</label>; }
export function Pagination({ page, pages, onPage }: { page: number; pages: number; onPage: (page: number) => void }) {
  if (pages <= 1) return null;
  return <nav className="v2-pagination" aria-label="Pagination"><button className="v2-button secondary compact" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Previous</button><span>Page {page} of {pages}</span><button className="v2-button secondary compact" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next →</button></nav>;
}

// Backend editor content is untrusted. Convert a small formatting allowlist to
// React nodes, never injecting HTML, inline styles or event attributes.
const allowedTags = new Set(['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'ul', 'ol', 'li', 'blockquote', 'h2', 'h3', 'h4', 'h5', 'hr', 'pre', 'code', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div']);
const droppedTags = new Set(['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'svg', 'math', 'link', 'meta', 'video', 'audio']);
function renderNode(node: Node, key: number): ReactNode {
  if (node.nodeType === 3) return node.textContent;
  if (node.nodeType !== 1) return null;
  const element = node as Element;
  const tag = element.tagName.toLowerCase();
  if (droppedTags.has(tag)) return null;
  const children = Array.from(element.childNodes).map(renderNode);
  if (!allowedTags.has(tag)) return <span key={key}>{children}</span>;
  const props: Record<string, unknown> = { key };
  if (tag === 'a') { props.href = safeUrl(element.getAttribute('href'), '#', true); props.rel = 'noopener noreferrer'; }
  if (tag === 'img') { const src = safeUrl(element.getAttribute('src'), ''); if (!src) return null; props.src = src; props.alt = element.getAttribute('alt') || ''; props.loading = 'lazy'; }
  return createElement(tag, props, ...(['img', 'br', 'hr'].includes(tag) ? [] : children));
}
export function RichText({ html }: { html?: string | null }) {
  const [content, setContent] = useState<ReactNode>(null);
  useEffect(() => { setContent(html ? Array.from(new DOMParser().parseFromString(html, 'text/html').body.childNodes).map(renderNode) : null); }, [html]);
  return <div className="v2-rich-text">{content || (html ? <p>{html.replace(/<[^>]*>/g, '')}</p> : null)}</div>;
}

type CaptchaApi = { ready: (fn: () => void) => void; render: (element: HTMLElement, settings: Record<string, unknown>) => number; reset: (id: number) => void };
declare global { interface Window { grecaptcha?: CaptchaApi; } }
let captchaLoading: Promise<void> | null = null;
export function Captcha({ siteKey, onToken, resetKey = 0 }: { siteKey: string; onToken: (token: string) => void; resetKey?: number }) {
  const container = useRef<HTMLDivElement>(null);
  const widget = useRef<number | null>(null);
  const callback = useRef(onToken);
  callback.current = onToken;
  const [failed, setFailed] = useState(false);
  const id = useId();
  useEffect(() => {
    if (!siteKey) return;
    let active = true;
    captchaLoading ??= new Promise<void>((resolve, reject) => {
      if (window.grecaptcha) { window.grecaptcha.ready(resolve); return; }
      const script = document.createElement('script');
      script.src = 'https://www.google.com/recaptcha/api.js?render=explicit'; script.async = true; script.defer = true;
      script.onload = () => window.grecaptcha?.ready(resolve);
      script.onerror = () => reject(new Error('Verification could not load.'));
      document.head.appendChild(script);
    });
    captchaLoading.then(() => {
      if (active && container.current && widget.current === null) widget.current = window.grecaptcha!.render(container.current, { sitekey: siteKey, theme: 'dark', callback: (token: string) => callback.current(token), 'expired-callback': () => callback.current(''), 'error-callback': () => { callback.current(''); setFailed(true); } });
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [siteKey]);
  useEffect(() => { if (widget.current !== null) { window.grecaptcha?.reset(widget.current); callback.current(''); } }, [resetKey]);
  return siteKey ? <div className="v2-captcha"><div id={id} ref={container} />{failed && <Notice error>Verification could not load. Check your connection and refresh this page.</Notice>}</div> : null;
}
