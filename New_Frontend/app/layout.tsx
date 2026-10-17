import type { Metadata } from 'next';
import './globals.css';
import './platform.css';
import './member-dashboard.css';
import './league-hub.css';
import './member-titles.css';
import './shop-catalog.css';
import './editor-applications.css';
import './home-motion.css';
import { SiteShell } from '@/components/platform/site-shell';

export const metadata: Metadata = {
  title: { default: 'Transformers — Create, Connect & Inspire', template: '%s | Transformers' },
  description: 'A home for editors, creative work, community stories, and discoveries.',
};

export default function RootLayout({ children }: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}
