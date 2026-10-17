'use client';

import { useSite } from './site-shell';

type AccountSection = 'dashboard' | 'profile' | 'league' | 'applications' | 'orders' | 'favorites' | 'notifications' | 'settings' | 'preferences';

export function AccountNav({ active }: { active: AccountSection }) {
  const { site } = useSite();
  const hasLeagueNavigation = site.navigation?.some(link => ['/editing-hub', '/editinghub', '/edithub'].includes(link.url.replace(/\/$/, '')));
  const links = [
    { key: 'dashboard', label: 'Dashboard', href: '/account' },
    { key: 'profile', label: 'Profile', href: '/account/profile' },
    ...(!hasLeagueNavigation ? [{ key: 'league', label: 'Editing Hub', href: '/editing-hub' }] : []),
    { key: 'applications', label: 'Applications', href: '/applications' },
    { key: 'orders', label: 'Orders', href: '/account/orders' },
    { key: 'favorites', label: 'Favorites', href: '/favorites' },
    { key: 'notifications', label: 'Notifications', href: '/notifications' },
    { key: 'settings', label: 'Settings', href: '/account/settings' },
  ];
  return <nav className="v2-member-nav" aria-label="Member navigation">{links.map(link => <a key={link.key} href={link.href} aria-current={(active === 'preferences' ? 'settings' : active) === link.key ? 'page' : undefined}>{link.label}</a>)}</nav>;
}
