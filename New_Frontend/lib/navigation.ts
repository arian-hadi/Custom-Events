/** Match the most specific local link, then the section owning a detail route. */
export function activeNavigationIndex(pathname: string | null, links: { url: string }[], origin?: string): number {
  if (!pathname) return -1;
  const clean = (path: string) => path.replace(/\/+$/, '') || '/';
  const current = clean(pathname);
  const paths = links.map(({ url }) => {
    if (!url || url.startsWith('#')) return null;
    try {
      if (url.startsWith('/') && !url.startsWith('//')) return clean(url.split(/[?#]/)[0]);
      const parsed = new URL(url);
      return origin && parsed.origin === origin ? clean(parsed.pathname) : null;
    } catch { return null; }
  });
  const match = (route: string) => paths.reduce((best, path, index) =>
    path && (route === path || (path !== '/' && route.startsWith(`${path}/`)))
      && (best < 0 || path.length > paths[best]!.length) ? index : best, -1);
  const direct = match(current);
  if (direct >= 0) return direct;
  const section = current.split('/')[1];
  const owners: Record<string, string> = {
    product: '/store', category: '/store',
    news: '/blog', 'news-posts': '/blog', 'news-categories': '/blog',
    contact: '/contact-us', editinghub: '/editing-hub', edithub: '/editing-hub',
    applications: '/account', favorites: '/account',
  };
  return owners[section] ? match(owners[section]) : -1;
}
