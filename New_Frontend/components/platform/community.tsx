'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { dateLabel, mutate, safeUrl, useResource, type Application, type CommunityEvent, type Notification, type PageResult } from '@/lib/api';
import { RequireAccount } from './auth';
import { AccountNav } from './account-nav';
import { MemberEditorApplications } from './member-dashboard';
import { useSite } from './site-shell';
import { Captcha, Empty, ErrorNotice, Field, Loading, Notice, PageHeading, Pagination, RichText } from './ui';

export function ContactPage() {
  const { user } = useSite();
  const config = useResource<{ recaptcha_site_key: string; recaptcha_enabled: boolean }>('contact/');
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [captcha, setCaptcha] = useState('');
  const [reset, setReset] = useState(0);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setError(null); setMessage('');
    try { const result = await mutate<{ detail?: string; message?: string }>('contact/', { ...Object.fromEntries(new FormData(form)), 'g-recaptcha-response': captcha }); setMessage(result.detail || result.message || 'Your message has been received. Thank you for getting in touch.'); form.reset(); }
    catch (error) { setError(error as Error); } finally { setBusy(false); setReset(value => value + 1); }
  }
  return <div className="v2-container v2-page"><PageHeading eyebrow="Let’s talk" title="Contact Us"><p>Have a question, idea, or something to share? We’d love to hear from you.</p></PageHeading><div className="v2-contact-grid"><div className="v2-contact-art"><img src="/assets/6c01245913-62b316a9c2f0390a3c62daeb_Group-3.png" alt="" /><h2>Good things start<br />with a conversation.</h2><p className="v2-muted">Send us a message and our team will get back to you.</p></div><div className="v2-panel"><ErrorNotice error={config.error} retry={config.reload} /><ErrorNotice error={error} />{message && <Notice>{message}</Notice>}<form className="v2-form" onSubmit={submit}><fieldset disabled={busy || config.loading || Boolean(config.error)}><div className="v2-form-row"><Field label="Your name"><input name="name" required maxLength={120} autoComplete="name" defaultValue={user?.username || ''} /></Field><Field label="Email address"><input name="email" type="email" required maxLength={150} autoComplete="email" defaultValue={user?.email || ''} /></Field></div><Field label="Subject"><input name="subject" required maxLength={150} /></Field><Field label="Message"><textarea name="message" required rows={6} maxLength={10000} /></Field><div className="v2-honeypot" aria-hidden="true"><label>Leave this field empty<input name="website" tabIndex={-1} autoComplete="off" /></label></div><Captcha siteKey={config.data?.recaptcha_enabled ? config.data.recaptcha_site_key : ''} onToken={setCaptcha} resetKey={reset} /><button className="v2-button" disabled={busy || Boolean(config.data?.recaptcha_enabled && !captcha)}>{busy ? 'Sending…' : 'Send message →'}</button></fieldset></form></div></div></div>;
}

export { EditingHubPage } from './league';

export function EventsPage() {
  const [page, setPage] = useState(1);
  const events = useResource<PageResult<CommunityEvent>>(`events/?page=${page}`);
  return <div className="v2-container v2-page"><PageHeading eyebrow="Get involved" title="Community events"><p>Find your next opportunity to create and connect.</p></PageHeading><ErrorNotice error={events.error} retry={events.reload} />{events.loading && <Loading label="Loading events…" />}{events.data && <>{events.data.results.length ? <div className="v2-two-columns">{events.data.results.map(event => <article className="v2-panel v2-event-card" key={event.id}><span className="v2-eyebrow">{event.deadline_passed ? 'Applications closed' : event.has_applied ? 'Applied' : 'Applications open'}</span><h2><a href={`/events/${event.id}`}>{event.title}</a></h2><RichText html={event.description} />{event.deadline && <p className="v2-small v2-muted">Apply by {dateLabel(event.deadline)}</p>}<a className="v2-arrow-link" href={`/events/${event.id}`}>View event →</a></article>)}</div> : <Empty title="More events soon">New opportunities will be listed here.</Empty>}<Pagination page={events.data.page} pages={events.data.pages} onPage={setPage} /></>}</div>;
}
export function EventPage({ id }: { id: string }) {
  const { user } = useSite();
  const event = useResource<{ event: CommunityEvent }>(`events/${encodeURIComponent(id)}/`);
  return <div className="v2-container v2-page"><a href="/events" className="v2-back-link">← Back to events</a><ErrorNotice error={event.error} retry={event.reload} />{event.loading && <Loading label="Loading event…" />}{event.data && <><PageHeading eyebrow="Community event" title={event.data.event.title}><p>{event.data.event.date && dateLabel(event.data.event.date)}{event.data.event.deadline && ` · Applications close ${dateLabel(event.data.event.deadline)}`}</p></PageHeading><div className="v2-contact-grid"><section><RichText html={event.data.event.description} /><RichText html={event.data.event.details} /></section><section className="v2-panel"><h2>Apply to join</h2>{event.data.event.has_applied ? <Notice>You’ve already applied. <a href="/applications">View your application →</a></Notice> : event.data.event.deadline_passed ? <Notice>Applications for this event are closed.</Notice> : !user ? <Notice><a href={`/login?next=${encodeURIComponent(`/events/${id}`)}`}>Sign in</a> to submit an application.</Notice> : <EventApplication event={event.data.event} />}</section></div></>}</div>;
}
function EventApplication({ event }: { event: CommunityEvent }) {
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  async function submit(formEvent: FormEvent<HTMLFormElement>) {
    formEvent.preventDefault(); setBusy(true); setError(null);
    const form = new FormData(formEvent.currentTarget);
    const values: Record<string, unknown> = { cover_letter: form.get('cover_letter') || '' };
    event.fields.forEach(field => { values[`field_${field.id}`] = field.field_type === 'boolean' ? form.has(`field_${field.id}`) : form.get(`field_${field.id}`); });
    try { await mutate(`events/${event.id}/apply/`, values); setSubmitted(true); }
    catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  if (submitted) return <Notice>Your application has been submitted. <a href="/applications">View your applications →</a></Notice>;
  return <><ErrorNotice error={error} /><form className="v2-form" onSubmit={submit}><fieldset disabled={busy}>{event.fields.map(field => field.field_type === 'boolean' ? <label className="v2-checkbox-row" key={field.id}><input name={`field_${field.id}`} type="checkbox" required={field.required} /><span>{field.name}</span></label> : <Field key={field.id} label={field.name}><input name={`field_${field.id}`} type={['number', 'date'].includes(field.field_type) ? field.field_type : 'text'} step={field.field_type === 'number' ? 'any' : undefined} required={field.required} /></Field>)}<Field label="Additional message (optional)"><textarea name="cover_letter" maxLength={10000} rows={4} /></Field><button className="v2-button" disabled={busy}>{busy ? 'Submitting…' : 'Submit application →'}</button></fieldset></form></>;
}
export function ApplicationsPage() { return <div className="v2-container v2-page"><AccountNav active="applications" /><PageHeading eyebrow="Your community activity" title="Your applications"><p>Your editor channels and event applications, together.</p></PageHeading><RequireAccount><div className="v2-stack"><MemberEditorApplications /><section aria-labelledby="event-applications-title"><h2 id="event-applications-title">Event applications</h2><ApplicationsList /></section></div></RequireAccount></div>; }
function ApplicationsList() {
  const [page, setPage] = useState(1);
  const [withdrawing, setWithdrawing] = useState<number | null>(null);
  const [confirmation, setConfirmation] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const applications = useResource<PageResult<Application>>(`applications/?page=${page}`);
  async function withdraw(id: number) {
    setWithdrawing(id); setError(null);
    try { await mutate(`applications/${id}/withdraw/`); setConfirmation(null); applications.reload(); }
    catch (error) { setError(error as Error); } finally { setWithdrawing(null); }
  }
  return <><ErrorNotice error={applications.error} retry={applications.reload} /><ErrorNotice error={error} />{applications.loading && <Loading />}{applications.data && <>{applications.data.results.length ? <div className="v2-stack">{applications.data.results.map(application => <article id={`event-${application.id}`} key={application.id} className="v2-panel"><div className="v2-section-heading"><h2><a href={`/events/${application.event.id}`}>{application.event.title}</a></h2><span className="v2-pill">{application.status}</span></div><p className="v2-small v2-muted">Applied {dateLabel(application.applied_date)}</p>{application.cover_letter && <p>{application.cover_letter}</p>}{application.responses.length > 0 && <dl className="v2-responses">{application.responses.map(response => <div key={response.field_id}><dt>{response.name}</dt><dd>{typeof response.value === 'boolean' ? response.value ? 'Yes' : 'No' : String(response.value ?? '—')}</dd></div>)}</dl>}<div className="v2-actions"><a className="v2-button secondary compact" href={`/applications/events/${application.id}`}>View application →</a>{application.edit_url && <a className="v2-text-button" href={safeUrl(application.edit_url)}>Edit application →</a>}{application.can_withdraw && <button className="v2-text-button" onClick={() => setConfirmation(application.id)} disabled={withdrawing !== null}>Withdraw application</button>}</div>{confirmation === application.id && <Notice>Withdraw your application to {application.event.title}?<div className="v2-actions"><button className="v2-button secondary compact" disabled={withdrawing !== null} onClick={() => setConfirmation(null)}>Keep application</button><button className="v2-button compact" disabled={withdrawing !== null} onClick={() => withdraw(application.id)}>{withdrawing === application.id ? 'Withdrawing…' : 'Confirm withdrawal'}</button></div></Notice>}</article>)}</div> : <Empty title="No applications yet"><a href="/events">Explore community events →</a></Empty>}<Pagination page={applications.data.page} pages={applications.data.pages} onPage={setPage} /></>}</>;
}

export function NotificationsPage() { return <div className="v2-container v2-page"><AccountNav active="notifications" /><PageHeading eyebrow="Stay in the loop" title="Your notifications"><p>Updates from across your community. <a href="/account/preferences">Manage preferences →</a></p></PageHeading><RequireAccount><NotificationsList /></RequireAccount></div>; }
function NotificationsList() {
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const notifications = useResource<PageResult<Notification> & { unread_count: number }>(`notifications/?page=${page}`);
  const { refreshUnread, unreadCount } = useSite();
  const reloadNotifications = notifications.reload;
  useEffect(() => { reloadNotifications(); }, [unreadCount, reloadNotifications]);
  async function markRead(id?: number) {
    setBusy(true); setError(null);
    try { await mutate(id ? `notifications/${id}/read/` : 'notifications/read-all/'); notifications.reload(); await refreshUnread(); }
    catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  return <><ErrorNotice error={notifications.error} retry={notifications.reload} /><ErrorNotice error={error} />{notifications.loading && <Loading />}{notifications.data && <><div className="v2-section-heading"><span className="v2-muted">{notifications.data.unread_count} unread</span><button className="v2-button secondary compact" disabled={busy || notifications.data.unread_count === 0} onClick={() => markRead()}>Mark all as read</button></div>{notifications.data.results.length ? <div className="v2-stack">{notifications.data.results.map(notification => <article key={notification.id} className={`v2-panel v2-notification${notification.is_read ? '' : ' unread'}`}><div><div className="v2-meta"><time dateTime={notification.created_at}>{dateLabel(notification.created_at)}</time>{!notification.is_read && <span className="v2-pill">New</span>}</div><h2>{safeUrl(notification.url || notification.link, '') ? <a href={safeUrl(notification.url || notification.link)} onClick={async event => { event.preventDefault(); if (!notification.is_read) { try { await mutate(`notifications/${notification.id}/read/`); } catch (error) { setError(error as Error); return; } } window.location.assign(safeUrl(notification.url || notification.link)); }}>{notification.title || 'Community update'}</a> : notification.title || 'Community update'}</h2><RichText html={notification.message} /></div>{!notification.is_read && <button className="v2-text-button" disabled={busy} onClick={() => markRead(notification.id)}>Mark as read</button>}</article>)}</div> : <Empty title="You’re all caught up">Your notifications will appear here.</Empty>}<Pagination page={notifications.data.page} pages={notifications.data.pages} onPage={setPage} /></>}</>;
}

export function AnnouncementsPage({ announcementId }: { announcementId?: string }) {
  const [page, setPage] = useState(1);
  const announcements = useResource<PageResult<{ id: number; title: string; message: string; thumbnail: string; image: string; created_at: string }>>(`announcements/?page=${page}${announcementId ? `&announcement=${encodeURIComponent(announcementId)}` : ''}`);
  return <div className="v2-container v2-page"><PageHeading eyebrow="From the team" title="Community announcements" /><ErrorNotice error={announcements.error} retry={announcements.reload} />{announcements.loading && <Loading />}{announcements.data && <>{announcements.data.results.length ? <div className="v2-stack">{announcements.data.results.map(announcement => <article id={`announcement-${announcement.id}`} key={announcement.id} className="v2-panel"><p className="v2-small v2-muted">{dateLabel(announcement.created_at)}</p><h2>{announcement.title}</h2>{safeUrl(announcement.image || announcement.thumbnail, '') && <img className="v2-article-image" src={safeUrl(announcement.image || announcement.thumbnail)} alt="" loading="lazy" />}<RichText html={announcement.message} /></article>)}</div> : <Empty title="No announcements yet" />}<Pagination page={announcements.data.page} pages={announcements.data.pages} onPage={setPage} /></>}</div>;
}



