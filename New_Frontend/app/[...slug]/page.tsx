import { notFound } from 'next/navigation';
import { AccountSettingsPage, AuthPage, PreferencesPage, type AuthMode, type Query } from '@/components/platform/auth';
import { MemberDashboardPage } from '@/components/platform/member-dashboard';
import { MemberProfilePage } from '@/components/platform/member-profile';
import { BlogPage, PostPage, ProductPage, StorePage } from '@/components/platform/catalog';
import { AnnouncementsPage, ApplicationsPage, ContactPage, EditingHubPage, EventPage, EventsPage, NotificationsPage } from '@/components/platform/community';
import { OrdersPage, OrderPage } from '@/components/platform/payments';
import { EditorApplyPage, EditorApplicationPage } from '@/components/platform/editor-applications';
import { EarlierEditsPage, EventApplicationPage } from '@/components/platform/member-activity';
import { LeaguePreviewPage } from '@/components/platform/league-preview';

type Props = { params: Promise<{ slug: string[] }>; searchParams: Promise<Query> };
const titles: Record<string, string> = { store: 'Store', product: 'Product', blog: 'Blog', news: 'Blog', 'news-posts': 'Article', 'news-categories': 'Blog', 'contact-us': 'Contact us', contact: 'Contact us', 'editing-hub': 'Editing Hub', events: 'Community events', applications: 'Your applications', account: 'Your account', notifications: 'Your notifications', favorites: 'Saved products', login: 'Sign in', register: 'Create an account', 'verify-email': 'Verify email', 'forgot-password': 'Password recovery', 'reset-password': 'Reset password', 'community-updates': 'Community announcements' };
export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const privatePage = (slug[0] === 'editing-hub' && ['apply', 'preview'].includes(slug[1])) || ['account', 'notifications', 'applications', 'favorites', 'login', 'register', 'verify-email', 'forgot-password', 'reset-password'].includes(slug[0]);
  const accountTitles: Record<string, string> = { settings: 'Account settings', profile: 'Your profile', orders: 'Your orders', preferences: 'Notification preferences' };
  const accountTitle = slug[0] === 'account' ? accountTitles[slug[1]] || 'Member dashboard' : null;
  return { title: (slug[0] === 'editing-hub' && slug[1] === 'apply' ? 'Become an editor' : accountTitle || titles[slug[0]]) || 'Community', ...(privatePage ? { robots: { index: false, follow: false } } : {}) };
}
export default async function ContentPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const query = await searchParams;
  const [section, detail] = slug;
  if (slug.length === 2 && section === 'editing-hub' && detail === 'preview') return <LeaguePreviewPage token={typeof query.token === 'string' ? query.token : ''} initialState={typeof query.state === 'string' ? query.state : undefined} />;
  if (slug.length === 1) {
    if (section === 'store') return <StorePage />;
    if (section === 'favorites') return <StorePage favorites />;
    if (['blog', 'news'].includes(section)) return <BlogPage />;
    if (['contact-us', 'contact'].includes(section)) return <ContactPage />;
    if (['editing-hub', 'editinghub', 'edithub'].includes(section)) return <EditingHubPage />;
    if (section === 'events') return <EventsPage />;
    if (section === 'applications') return <ApplicationsPage />;
    if (section === 'notifications') return <NotificationsPage />;
    if (section === 'community-updates') return <AnnouncementsPage announcementId={typeof query.announcement === 'string' ? query.announcement : undefined} />;
    if (section === 'account') return <MemberDashboardPage />;
    if (['login', 'register', 'verify-email', 'forgot-password', 'reset-password'].includes(section)) return <AuthPage mode={section as AuthMode} query={query} />;
  }
  if (slug.length === 2) {
    if (section === 'editing-hub' && detail === 'apply') return <EditorApplyPage initialPlatform={typeof query.platform === 'string' ? query.platform : typeof query.edit_platform === 'string' ? query.edit_platform : undefined} />;
    if (section === 'account' && detail === 'settings') return <AccountSettingsPage query={query} />;
    if (section === 'account' && detail === 'profile') return <MemberProfilePage />;
    if (section === 'account' && detail === 'edits') return <EarlierEditsPage />;
    if (section === 'account' && detail === 'preferences') return <PreferencesPage />;
    if (section === 'account' && detail === 'orders') return <OrdersPage />;
    if (section === 'product' && /^\d+$/.test(detail)) return <ProductPage id={detail} />;
    if (['blog', 'news-posts'].includes(section)) return <PostPage slug={detail} />;
    if (section === 'category') return <StorePage initialCategory={detail} />;
    if (section === 'news-categories') return <BlogPage initialCategory={detail} />;
    if (section === 'events' && /^\d+$/.test(detail)) return <EventPage id={detail} />;
  }
  if (slug.length === 3 && section === 'applications' && detail === 'editors' && /^\d+$/.test(slug[2])) return <EditorApplicationPage id={slug[2]} />;
  if (slug.length === 3 && section === 'applications' && detail === 'events' && /^\d+$/.test(slug[2])) return <EventApplicationPage id={slug[2]} />;
  if (slug.length === 3 && section === 'account' && detail === 'edits' && /^\d+$/.test(slug[2])) return <EarlierEditsPage id={slug[2]} />;
  if (slug.length === 3 && section === 'account' && detail === 'orders' && /^[0-9a-f-]{36}$/i.test(slug[2])) return <OrderPage id={slug[2]} returnedFromCheckout={query.checkout === 'success' || query.checkout === 'cancelled'} />;
  notFound();
}
