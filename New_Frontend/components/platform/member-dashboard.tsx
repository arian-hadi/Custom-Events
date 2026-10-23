'use client';

import { EditorTitle } from './editor-title';

import { useState, type ReactNode } from 'react';
import { ArrowRight, ArrowUpRight, BadgeCheck, Bell, Check, Clock3, Film, Flag, Heart, Package, RefreshCw, Settings2, Trophy, UserRound } from 'lucide-react';
import { dateLabel, safeUrl, useResource } from '@/lib/api';
import { currencyLabel, paymentStatusLabel } from '@/lib/commerce';
import { leagueNumber, leagueStateLabel, pointsLabel } from '@/lib/league-view';
import { applicationStatus, dashboardAttention, submissionDeadline, type EditorApplicationSummary, type MemberDashboard } from '@/lib/member-dashboard';
import { AccountNav } from './account-nav';
import { RequireAccount } from './auth';
import { ErrorNotice, Loading } from './ui';

function dateTime(value: string | null | undefined) {
  if (!value || Number.isNaN(Date.parse(value))) return '';
  return new Date(value).toLocaleString('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }) + ' UTC';
}

function Status({ children, emphasized = false }: { children: ReactNode; emphasized?: boolean }) {
  return <span className={`v2-member-status${emphasized ? ' emphasized' : ''}`}>{children}</span>;
}

function PanelHeading({ eyebrow, title, id, children }: { eyebrow?: string; title: string; id?: string; children?: ReactNode }) {
  return <div className="v2-member-panel-heading"><div>{eyebrow && <span className="v2-eyebrow">{eyebrow}</span>}<h2 id={id}>{title}</h2></div>{children}</div>;
}

function ProfileImage({ src, name }: { src: string | null; name: string }) {
  const [failed, setFailed] = useState(false);
  return <div className="v2-member-avatar">{!failed && safeUrl(src, '') ? <img src={safeUrl(src)} alt="" onError={() => setFailed(true)} width={76} height={76} /> : <span aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>}</div>;
}

export function MemberDashboardPage() {
  return <div className="v2-container v2-page v2-member-page"><RequireAccount><Dashboard /></RequireAccount></div>;
}

function Dashboard() {
  const resource = useResource<MemberDashboard>('member/dashboard/');
  const data = resource.data;
  return <>
    <AccountNav active="dashboard" />
    <ErrorNotice error={resource.error} retry={resource.reload} />
    {resource.loading && <Loading label="Loading your member dashboard…" />}
    {data && <DashboardContent data={data} onRefresh={resource.reload} />}
  </>;
}

export function DashboardContent({ data, onRefresh }: { data: MemberDashboard; onRefresh?: () => void }) {
  return <>
      <header className="v2-member-identity">
        <div className="v2-member-identity-main"><ProfileImage key={data.member.profile_picture} src={data.member.profile_picture} name={data.member.display_name || data.member.username} /><div className="v2-member-name"><span className="v2-eyebrow">Member dashboard</span><h1>{data.member.display_name || data.member.username}</h1><div className="v2-member-identity-meta"><EditorTitle name={data.member.editor_title || (data.member.verified_editor ? 'Community editor' : 'Community member')} rarity={data.member.editor_title_rarity} />{data.member.verified_editor && <Status emphasized><BadgeCheck size={14} aria-hidden="true" /> Verified editor</Status>}</div></div></div>
        <div className="v2-member-header-side">{leagueNumber(data.league.month.points) !== null && <div className="v2-member-season"><Trophy size={17} aria-hidden="true" /><div><strong>{pointsLabel(data.league.month.points)} <span>points</span></strong><span>{data.league.month.label || 'Current month'}{data.league.month.rank !== null && ` · #${data.league.month.rank}`}</span></div></div>}<a className="v2-button secondary compact" href="/account/profile"><UserRound size={15} aria-hidden="true" /> Edit profile</a>{data.member.verified_editor && <a className="v2-member-inline-link" href="/account/profile#editor-title">Change title <ArrowRight size={14} aria-hidden="true" /></a>}</div>
      </header>
      <div className="v2-member-overview-label"><p>Your activity, your edits, your next move.</p><div><time className="v2-small v2-muted" dateTime={data.generated_at}>Updated {dateTime(data.generated_at)}</time>{onRefresh && <button className="v2-text-button v2-member-refresh" onClick={onRefresh} aria-label="Refresh member dashboard"><RefreshCw size={14} aria-hidden="true" /> Refresh</button>}</div></div>
      <Attention data={data} />
      <div className="v2-member-grid">
        <Competition data={data} />
        <LatestEdit data={data} />
        <Applications data={data} />
        <Notifications data={data} />
        {data.orders.length > 0 && <Orders data={data} />}
      </div>
      <QuickAccess data={data} />
  </>;
}

function Attention({ data }: { data: MemberDashboard }) {
  const items = dashboardAttention(data);
  return <section className="v2-member-attention" aria-labelledby="member-attention-title"><div className="v2-member-attention-heading"><span className="v2-member-indicator" aria-hidden="true" /><h2 id="member-attention-title">Needs your attention</h2></div>{items.length ? <div className="v2-member-attention-items">{items.map(item => <a key={item.key} className={`v2-member-attention-item${item.urgent ? ' urgent' : ''}`} href={safeUrl(item.href, '/account')}><div><span>{item.label}</span><strong>{item.detail}</strong></div><ArrowUpRight size={16} aria-hidden="true" /></a>)}</div> : <p className="v2-member-caught-up"><Check size={16} aria-hidden="true" /> You’re all caught up. Your next updates will appear here.</p>}</section>;
}

function Competition({ data }: { data: MemberDashboard }) {
  const league = data.league;
  const result = league.latest_result;
  const entryOpen = league.enabled && league.configuration_ready && league.can_submit;
  const deadline = submissionDeadline(league.submission_deadline, data.generated_at);
  const hasRank = league.month.rank !== null;
  return <section className="v2-panel v2-member-competition" aria-labelledby="member-league-title">
    <div className="v2-member-competition-art" aria-hidden="true"><Flag /></div>
    <PanelHeading eyebrow="Make every round count" title={`${league.month.label} editing league`} id="member-league-title"><span className="v2-member-icon"><Trophy size={21} aria-hidden="true" /></span></PanelHeading>
    <div className="v2-member-rankboard"><div><span className="v2-member-metric-label">League position</span><strong className={`v2-member-rank${hasRank ? '' : ' unranked'}`}>{hasRank ? <><span>#</span>{league.month.rank}</> : 'Unranked'}</strong>{league.rank_change !== null && <span className="v2-small">{league.rank_change > 0 ? `↑ ${league.rank_change} places gained` : league.rank_change < 0 ? `↓ ${Math.abs(league.rank_change)} places lost` : 'Position unchanged'}</span>}</div><div><span className="v2-member-metric-label">League points</span><strong className="v2-member-points">{pointsLabel(league.month.points)}</strong><span className="v2-small v2-muted">{league.month.scored_rounds ? `From ${league.month.scored_rounds} scored ${league.month.scored_rounds === 1 ? 'round' : 'rounds'}` : 'No official ranking yet'}</span></div></div>
    {result ? <div className="v2-member-latest-result"><span><Trophy size={15} aria-hidden="true" /> Latest official result</span><strong>{result.rank !== null ? `#${result.rank}` : 'Result recorded'}{leagueNumber(result.points) !== null && ` · ${pointsLabel(result.points)} points`}</strong><span className="v2-small v2-muted">{result.period_label}</span></div> : <p className="v2-member-ranking-note">Results will appear after scoring. Each official round builds your league standing.</p>}
    <div className="v2-member-rounds">
      {league.current_week && <div className="v2-member-round"><span className="v2-member-metric-label">Current round</span><strong>{league.current_week.label}</strong><span className="v2-small v2-muted">{league.current_entry ? `Your entry: ${leagueStateLabel(league.current_entry.state)}` : 'You have no entry in this round'} · {leagueStateLabel(league.current_week.state)}</span>{league.current_entry && <a className="v2-member-inline-link" href={safeUrl(league.current_entry.detail_url, '/editing-hub#league-entry')}>View current entry <ArrowRight size={13} aria-hidden="true" /></a>}</div>}
      {league.next_week ? <div className="v2-member-round v2-member-next-round"><div><span className="v2-member-metric-label">Next round</span><strong>{league.next_week.label}</strong></div><Status emphasized={entryOpen}>{league.next_entry ? leagueStateLabel(league.next_entry.state) : entryOpen ? 'Entries open' : 'Entries unavailable'}</Status><div className="v2-member-deadline"><Clock3 size={15} aria-hidden="true" /><div><strong>{entryOpen && deadline ? deadline : 'Entry deadline'}</strong>{league.submission_deadline && <time dateTime={league.submission_deadline}>{dateTime(league.submission_deadline)}</time>}</div></div></div> : <p className="v2-small v2-muted">The next competition has not been scheduled yet.</p>}
    </div>
    {(!league.enabled || !league.configuration_ready) && <p className="v2-member-ranking-note">{!league.enabled ? 'The league is not open yet. Check back for the next competition.' : 'Official scoring is being prepared. Results will appear once scoring is ready.'}</p>}
    <div className="v2-member-competition-actions"><a className="v2-button secondary compact" href="/editing-hub#league-standings-title">View league <ArrowUpRight size={15} aria-hidden="true" /></a>{league.next_entry ? <a className="v2-button compact" href={safeUrl(league.next_entry.detail_url, '/editing-hub#league-entry')}>Manage edit <ArrowRight size={15} aria-hidden="true" /></a> : entryOpen && data.member.verified_editor ? <a className="v2-button compact" href="/editing-hub#league-entry">Submit edit <ArrowRight size={15} aria-hidden="true" /></a> : !data.member.verified_editor ? <a className="v2-member-inline-link" href="/editing-hub/apply">Become an editor <ArrowRight size={14} aria-hidden="true" /></a> : null}</div>
  </section>;
}

function EditPreview({ edit }: { edit: NonNullable<MemberDashboard['latest_edit']> }) {
  const [failed, setFailed] = useState(false);
  const image = safeUrl(edit.thumbnail, '');
  return <a href={safeUrl(edit.detail_url, '/editing-hub#league-entry')} className="v2-member-edit-preview" aria-label={`View submission: ${edit.title || 'Your latest edit'}`}>
    {image && !failed ? <img src={image} alt={edit.title || 'Your submitted edit'} onError={() => setFailed(true)} loading="lazy" width={640} height={360} /> : <div className="v2-member-edit-placeholder"><span className="v2-member-edit-frame" aria-hidden="true"><Film size={38} strokeWidth={1.2} /></span><span className="v2-eyebrow">{edit.platform} edit</span><strong>{edit.title || 'Your latest edit'}</strong><span>Preview unavailable · View submission <ArrowUpRight size={13} aria-hidden="true" /></span></div>}
    {image && !failed && <span className="v2-member-media-link"><ArrowUpRight size={19} aria-hidden="true" /></span>}
    <span className="v2-member-media-platform">{edit.platform}</span>
  </a>;
}

function LatestEdit({ data }: { data: MemberDashboard }) {
  const edit = data.latest_edit;
  const stats = data.edit_stats;
  return <section className="v2-panel v2-member-edit" aria-labelledby="member-latest-edit-title"><PanelHeading eyebrow="Your creative work" title="Latest edit" id="member-latest-edit-title" />{edit ? <>
    <EditPreview key={`${edit.source}-${edit.id}-${edit.thumbnail}`} edit={edit} />
    <div className="v2-member-edit-body"><div className="v2-member-edit-meta"><time dateTime={edit.submitted_at}>Submitted {dateLabel(edit.submitted_at)}</time><Status>{edit.source === 'legacy' ? 'Earlier submission' : leagueStateLabel(edit.state)}</Status></div><h3>{edit.title || 'Your latest edit'}</h3>
      {(edit.rank !== null || leagueNumber(edit.league_points) !== null || edit.upvotes !== null) && <dl className="v2-member-edit-results">{edit.rank !== null && <div><dt>Round position</dt><dd>#{edit.rank}</dd></div>}{leagueNumber(edit.league_points) !== null && <div><dt>League points</dt><dd>{pointsLabel(edit.league_points)}</dd></div>}{edit.upvotes !== null && <div><dt>Upvotes</dt><dd>{pointsLabel(edit.upvotes)}</dd></div>}</dl>}
      {edit.source === 'league' && edit.rank === null && <p className="v2-small v2-muted">{['withdrawn', 'invalid', 'disqualified'].includes(edit.state) ? 'This submission has no official result.' : 'Your official result will appear after scoring.'}</p>}
      {edit.source === 'legacy' && <p className="v2-small v2-muted">From your earlier submissions. League results are shown on league entries.</p>}
      <a className="v2-member-inline-link" href={safeUrl(edit.detail_url, '/editing-hub#league-entry')}>View submission <ArrowUpRight size={15} aria-hidden="true" /></a>
    </div>
    <dl className="v2-member-creative-stats"><div><dt>League entries</dt><dd>{stats.league_submissions}</dd></div>{stats.best_league_result !== null && <div><dt>Best league result</dt><dd>#{stats.best_league_result}</dd></div>}{leagueNumber(stats.league_points) !== null && <div><dt>Career league points</dt><dd>{pointsLabel(stats.league_points)}</dd></div>}</dl>
    {stats.legacy_submissions > 0 && <details className="v2-member-history"><summary>Earlier edit activity <span>{stats.legacy_submissions} submissions</span></summary><dl className="v2-member-creative-stats"><div><dt>Earlier submissions</dt><dd>{stats.legacy_submissions}</dd></div><div><dt>Verified</dt><dd>{stats.legacy_verified}</dd></div><div><dt>Upvotes</dt><dd>{pointsLabel(stats.legacy_upvotes)}</dd></div></dl><a className="v2-member-inline-link" href="/account/edits">Manage earlier edits <ArrowUpRight size={13} aria-hidden="true" /></a></details>}
  </> : <div className="v2-member-first-edit"><div className="v2-member-edit-frame" aria-hidden="true"><Film size={38} strokeWidth={1.2} /></div><h3>Your first edit starts here.</h3><p>Give your work a place in the community. Join a competition and your latest submission will appear here.</p><a className="v2-button secondary compact" href={data.member.verified_editor ? '/editing-hub#league-entry' : '/editing-hub/apply'}>{data.member.verified_editor ? 'Explore competitions' : 'Become an editor'} <ArrowRight size={15} aria-hidden="true" /></a></div>}</section>;
}

export function EditorApplicationsPanel({ editors, compact = false }: { editors: EditorApplicationSummary[]; compact?: boolean }) {
  const applications = editors.filter(application => application.id !== null && application.status !== 'not_applied');
  return <div className={`v2-member-editor-apps${compact ? ' compact' : ''}`}>{applications.length ? applications.map(application => <a className="v2-member-application-row" href={safeUrl(application.url, '/applications')} key={application.id}><div><strong>{application.platform.toLowerCase() === 'youtube' ? 'YouTube' : application.platform.toLowerCase() === 'tiktok' ? 'TikTok' : application.platform} Editor</strong><span>{application.channel_name || 'Editor application'}{application.removal_requested && ' · Removal requested'}</span></div><Status emphasized={application.status === 'accepted' && application.channel_verified}>{application.status === 'accepted' && application.channel_verified && <BadgeCheck size={12} aria-hidden="true" />}{['pending', 'accepted'].includes(application.status) && !application.channel_verified && !application.removal_requested ? 'Confirm channel' : applicationStatus(application.status)}</Status><ArrowUpRight size={14} aria-hidden="true" /></a>) : <p className="v2-member-small-empty">Apply with one YouTube or TikTok channel. <a href="/editing-hub/apply">Become an editor <ArrowRight size={12} aria-hidden="true" /></a></p>}</div>;
}

export function MemberEditorApplications() {
  const resource = useResource<MemberDashboard>('member/dashboard/');
  return <section className="v2-panel v2-member-application-section"><PanelHeading title="Editor applications" eyebrow="Your community channels" /><ErrorNotice error={resource.error} retry={resource.reload} />{resource.loading && <Loading label="Loading editor applications…" />}{resource.data && <EditorApplicationsPanel editors={resource.data.applications.editors} />}</section>;
}

function Applications({ data }: { data: MemberDashboard }) {
  return <section className="v2-panel v2-member-applications" aria-labelledby="member-applications-title"><PanelHeading title="Applications" id="member-applications-title"><a className="v2-member-inline-link" href="/applications">View all <ArrowRight size={14} aria-hidden="true" /></a></PanelHeading><h3 className="v2-member-subheading">Editor applications</h3><EditorApplicationsPanel editors={data.applications.editors} compact /><div className="v2-member-event-apps"><h3 className="v2-member-subheading">Event applications{data.applications.event_count > 0 && <span>{data.applications.event_count}</span>}</h3>{data.applications.events.length ? data.applications.events.slice(0, 3).map(application => <a className="v2-member-application-row" key={application.id} href={safeUrl(application.url, '/applications')}><div><strong>{application.title}</strong><span>Applied {dateLabel(application.applied_at)}</span></div><Status>{applicationStatus(application.status)}</Status><ArrowUpRight size={14} aria-hidden="true" /></a>) : <p className="v2-member-small-empty">No event applications yet. <a href="/events">Explore community events <ArrowRight size={12} aria-hidden="true" /></a></p>}</div></section>;
}

function Notifications({ data }: { data: MemberDashboard }) {
  return <section className="v2-panel v2-member-notifications" aria-labelledby="member-notifications-title"><PanelHeading title="Notifications" id="member-notifications-title">{data.notifications.unread_count > 0 && <Status emphasized>{data.notifications.unread_count} unread</Status>}</PanelHeading>{data.notifications.results.length ? <ul className="v2-member-notification-list">{data.notifications.results.slice(0, 4).map(item => <li key={item.id}><a href={safeUrl(item.url || item.link, '/notifications')} className={item.is_read ? '' : 'unread'}><span className="v2-member-notification-dot" aria-label={item.is_read ? 'Read' : 'Unread'} /><div>{item.title && <strong>{item.title}</strong>}<p>{item.message.replace(/<[^>]*>/g, '')}</p><time dateTime={item.created_at}>{dateLabel(item.created_at)}</time></div><ArrowUpRight size={13} aria-hidden="true" /></a></li>)}</ul> : <div className="v2-member-notification-empty"><Bell size={26} strokeWidth={1.3} aria-hidden="true" /><h3>{data.notifications.unread_count ? 'Your inbox has earlier updates.' : 'You’re up to date.'}</h3><p>{data.notifications.unread_count ? 'Open notifications to review your account history.' : 'Application decisions and community updates will appear here.'}</p></div>}<a className="v2-member-inline-link v2-member-panel-footer" href="/notifications">View all notifications <ArrowRight size={14} aria-hidden="true" /></a></section>;
}

function Orders({ data }: { data: MemberDashboard }) {
  return <section className="v2-panel v2-member-orders" aria-labelledby="member-orders-title"><PanelHeading title="Recent orders" id="member-orders-title"><a className="v2-member-inline-link" href="/account/orders">View all <ArrowRight size={14} aria-hidden="true" /></a></PanelHeading><div className="v2-member-order-grid">{data.orders.slice(0, 3).map(order => <article className="v2-member-order" key={order.id}><div className="v2-member-order-icon" aria-hidden="true"><Package size={22} strokeWidth={1.4} /></div><div><span className="v2-member-metric-label">Order {order.id.length > 12 ? `${order.id.slice(0, 8)}…` : `#${order.id}`}</span><h3>{order.product_name}</h3><p className="v2-small v2-muted">{currencyLabel(order.display_amount, order.currency)} · {dateLabel(order.created_at)}</p><Status>{order.status === 'paid' ? order.fulfillment_status === 'fulfilled' ? 'Fulfilled' : 'Awaiting fulfillment' : paymentStatusLabel(order.status)}</Status>{order.fulfillment_note && <p className="v2-member-order-note">{order.fulfillment_note}</p>}<a href={safeUrl(order.url, `/account/orders/${order.id}`)} className="v2-member-inline-link">View order <ArrowRight size={13} aria-hidden="true" /></a></div></article>)}</div></section>;
}

function QuickAccess({ data }: { data: MemberDashboard }) {
  return <section className="v2-member-quick-access" aria-labelledby="member-quick-title"><h2 id="member-quick-title">Quick access</h2><nav aria-label="Account shortcuts"><a href="/favorites"><Heart size={14} aria-hidden="true" /> Favorites{data.favorites_count > 0 && <span>{data.favorites_count}</span>}</a><a href="/account/orders"><Package size={14} aria-hidden="true" /> Orders</a><a href="/applications">Applications</a><a href="/notifications"><Bell size={14} aria-hidden="true" /> Notifications</a><a href="/account/profile"><UserRound size={14} aria-hidden="true" /> Profile</a><a href="/account/settings"><Settings2 size={14} aria-hidden="true" /> Account settings</a><a href="/account/preferences">Email & notification preferences</a></nav></section>;
}

