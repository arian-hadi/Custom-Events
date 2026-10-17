'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowUpRight, Coffee, Mail, UserRound } from 'lucide-react';
import { api, mutate, safeUrl, useResource, type Session, type Site, type User } from '@/lib/api';
import { ErrorNotice } from './ui';
import { activeNavigationIndex } from '@/lib/navigation';
import footerStyles from './site-footer.module.css';

export const fallbackSite: Site = {
  name: 'Transformers', accent_color: '#ef233c', secondary_accent_color: '#ffb800', hero_title: 'Create, Improve\n& Inspire',
  hero_subtitle: 'A home for editors, creative work, and the community behind it.', hero_image: '',
  hero_button_text: 'Explore the community', hero_button_url: '/editing-hub', logo: '', favicon: '',
  footer_text: 'A place to create, share, and grow together.',
  navigation: [{ label: 'Home', url: '/' }, { label: 'Store', url: '/store' }, { label: 'Blog', url: '/blog' }, { label: 'Editing Hub', url: '/editing-hub' },
    // Events are temporarily hidden; their routes and application history remain available.
    // { label: 'Events', url: '/events' },
    { label: 'Contact', url: '/contact-us' }], social_links: [],
};
type SiteContextValue = { site: Site; siteLoading: boolean; siteError: Error | null; user: User | null; session: Session | null; sessionLoading: boolean; sessionError: Error | null; refreshSession: () => Promise<void>; unreadCount: number; refreshUnread: () => Promise<void> };
const SiteContext = createContext<SiteContextValue | null>(null);
export function useSite() { const value = useContext(SiteContext); if (!value) throw new Error('Missing site context'); return value; }

function isEventNavigation(link: { label: string; url: string }) {
  if (link.label.trim().toLowerCase() === 'events') return true;
  try { return /^\/events(?:\/|$)/i.test(new URL(link.url, 'https://local.invalid').pathname); }
  catch { return false; }
}

function configuredCoffeeUrl(value?: string) {
  try {
    const url = new URL(safeUrl(value, ''));
    return url.protocol === 'https:' && ['buymeacoffee.com', 'www.buymeacoffee.com'].includes(url.hostname)
      && !url.username && !url.password && url.pathname !== '/' ? url.href : '';
  } catch { return ''; }
}

export function SiteShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [origin, setOrigin] = useState<string>();
  const menuButton = useRef<HTMLButtonElement>(null);
  const configuration = useResource<{ site: Site }>('site/');
  const [session, setSession] = useState<Session | null>(null);
  const [sessionError, setSessionError] = useState<Error | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<Error | null>(null);
  useEffect(() => { setOrigin(window.location.origin); }, []);
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); menuButton.current?.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen]);
  const site = { ...fallbackSite, ...configuration.data?.site };
  const refreshSession = useCallback(async () => {
    try { setSession(await api<Session>('auth/session/')); setSessionError(null); }
    catch (error) { setSession(null); setSessionError(error as Error); }
    finally { setSessionLoading(false); }
  }, []);
  useEffect(() => { void refreshSession(); }, [refreshSession]);
  const user = session?.user || null;
  const userId = user?.id;
  const refreshUnread = useCallback(async () => {
    if (!userId) { setUnreadCount(0); return; }
    try { const result = await api<{ unread_count: number }>('notifications/'); setUnreadCount(result.unread_count); } catch { /* Full notifications page surfaces any loading failure. */ }
  }, [userId]);
  useEffect(() => {
    void refreshUnread();
    const timer = window.setInterval(() => { if (!document.hidden) void refreshUnread(); }, 60000);
    const onVisible = () => { if (!document.hidden) { void refreshSession(); void refreshUnread(); } };
    document.addEventListener('visibilitychange', onVisible);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisible); };
  }, [refreshUnread, refreshSession]);
  useEffect(() => {
    const favicon = safeUrl(site.favicon, '');
    if (!favicon) return;
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link); }
    link.href = favicon;
  }, [site.favicon]);
  async function logout() {
    setLogoutError(null);
    try { await mutate('auth/logout/'); await refreshSession(); window.location.assign('/'); }
    catch (error) { setLogoutError(error as Error); }
  }
  const accent = /^#[0-9a-f]{6}$/i.test(site.accent_color) ? site.accent_color : fallbackSite.accent_color;
  const secondaryAccent = /^#[0-9a-f]{6}$/i.test(site.secondary_accent_color || '') ? site.secondary_accent_color : fallbackSite.secondary_accent_color;
  // Also hide Events when links are supplied by the admin's navigation configuration.
  const configuredNavigation = (Array.isArray(site.navigation) && site.navigation.length ? site.navigation : fallbackSite.navigation)
    .filter(link => !isEventNavigation(link));
  const coffeeUrl = configuredCoffeeUrl(site.buy_me_a_coffee_url);
  const navigation = user
    ? configuredNavigation.map(link => link.url === '/' || link.label.toLowerCase() === 'home' ? { label: 'Dashboard', url: '/account' } : link)
      .filter((link, index, links) => links.findIndex(item => item.url === link.url) === index)
    : configuredNavigation;
  const activeIndex = activeNavigationIndex(pathname, navigation, origin);
  const accountActive = pathname === '/account' || pathname?.startsWith('/account/');
  return <SiteContext.Provider value={{ site, siteLoading: configuration.loading, siteError: configuration.error, session, user, sessionLoading, sessionError, refreshSession, unreadCount, refreshUnread }}>
    <div className="platform" style={{ '--accent': accent, '--magenta': accent, '--secondary-accent': secondaryAccent } as CSSProperties}>
      <a href="#main-content" className="v2-skip-link">Skip to content</a>
      <header className="v2-header"><div className="v2-container v2-nav-row">
        <a href="/" className="v2-brand" aria-label={`${site.name} home`}><img src={safeUrl(site.logo, '/assets/39a2713f12-62ac88bb57b859791be72386_Logo-playo.png')} alt="" width={40} height={40} /><span>{site.name}</span></a>
        <button ref={menuButton} className="v2-menu-button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? '✕' : '☰'}</button>
        <nav id="primary-navigation" className={`v2-nav${menuOpen ? ' open' : ''}`} aria-label="Main navigation">{navigation.map((link, index) => <Link prefetch={false} key={`${link.label}-${link.url}`} href={safeUrl(link.url)} aria-current={index === activeIndex ? 'page' : undefined} onClick={() => setMenuOpen(false)}>{link.label}</Link>)}</nav>
        <div className="v2-account-nav">{user ? <><a href="/notifications" className="v2-notification-link" aria-current={pathname === '/notifications' ? 'page' : undefined} aria-label={`Notifications, ${unreadCount} unread`}><span aria-hidden="true">♧</span>{unreadCount > 0 && <span className="v2-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>}</a><a href="/account" className="v2-button secondary compact v2-member-account-link" data-active={accountActive || undefined} aria-label={`${user.username} · Member dashboard`}><UserRound size={17} aria-hidden="true" /><span>{user.username}</span></a><button onClick={logout} className="v2-text-button">Sign out</button></> : <a href="/login" className="v2-button secondary compact" aria-current={pathname === '/login' ? 'page' : undefined}>{sessionLoading ? 'Account' : 'Sign in'} <span aria-hidden="true">↗</span></a>}</div>
      </div></header>
      {logoutError && <div className="v2-container"><ErrorNotice error={logoutError} /></div>}
      <main id="main-content">{children}</main>
      <footer className={footerStyles.footer}><div className="v2-container">
        <div className={footerStyles.communityLine}><span>For the love of creating.</span><a href="/editing-hub">Meet the editing community <ArrowUpRight size={16} aria-hidden="true" /></a></div>
        <div className={footerStyles.grid}>
          <div className={footerStyles.brandColumn}>
            <a href="/" className="v2-brand"><img src={safeUrl(site.logo, '/assets/39a2713f12-62ac88bb57b859791be72386_Logo-playo.png')} alt="" width={40} height={40} /><span>{site.name}</span></a>
            <p>{site.footer_text}</p>
            {coffeeUrl && <a className={`v2-button secondary compact ${footerStyles.coffee}`} href={coffeeUrl} target="_blank" rel="noopener noreferrer"><Coffee size={21} aria-hidden="true" /><span>Buy me a coffee</span><ArrowUpRight size={15} aria-hidden="true" /></a>}
          </div>
          <nav className={footerStyles.links} aria-label="Explore the website"><h2>Explore</h2><a href="/store">Shop</a><a href="/blog">Blog</a><a href="/editing-hub">Editing Hub</a>
            {/* Temporarily hidden: <a href="/events">Events</a>. Existing event routes and records are preserved. */}
            <a href="/community-updates">Announcements</a>
          </nav>
          <nav className={footerStyles.links} aria-label="Your community account"><h2>Your space</h2><a href="/account">Member dashboard</a><a href="/favorites">Saved products</a><a href="/applications">Your applications</a><a href="/account/preferences">Email preferences</a>{user?.is_staff && <a href="/admin/">Administration ↗</a>}</nav>
          <div className={footerStyles.contactColumn}>
            <span className="v2-eyebrow">Stay connected</span><h2>Good things start with a conversation.</h2><p>A question, an idea, or a collaboration? We’d love to hear from you.</p>
            <a className={`v2-button ${footerStyles.contactButton}`} href="/contact-us">Contact us <ArrowUpRight size={18} aria-hidden="true" /></a>
            <a href="/account/preferences" className={footerStyles.emailPreferences}><Mail size={19} aria-hidden="true" /><span>News, edits & community updates<small>Choose the emails you receive →</small></span></a>
          </div>
        </div>
        {site.social_links?.some(link => safeUrl(link.url, '')) && <nav className={footerStyles.socials} aria-label="Follow the community"><span>Find us around the web</span>{site.social_links.filter(link => safeUrl(link.url, '')).map(link => <a key={`${link.label}-${link.url}`} href={safeUrl(link.url)} rel="noopener noreferrer" target="_blank">{link.label}<ArrowUpRight size={14} aria-hidden="true" /></a>)}</nav>}
        <div className={footerStyles.bottom}><span>© {new Date().getFullYear()} {site.name}</span><nav aria-label="Information"><a href="/about/">About</a><a href="/terms/">Terms</a><a href="/privacy/">Privacy</a><a href="/disclaimers/">Disclaimers</a></nav><span>Original design by <a href="https://www.128.digital/" target="_blank" rel="noopener noreferrer">128.digital</a></span></div>
      </div></footer>
    </div>
  </SiteContext.Provider>;
}
