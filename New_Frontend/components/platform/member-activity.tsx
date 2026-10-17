'use client';

import Link from 'next/link';
import { useState, type SubmitEvent } from 'react';
import { dateLabel, mutate, safeUrl, useResource, type Application, type PageResult } from '@/lib/api';
import { RequireAccount } from './auth';
import { AccountNav } from './account-nav';
import { Empty, ErrorNotice, Field, Loading, Notice, PageHeading, Pagination } from './ui';

export function EventApplicationPage({ id }: { id: string }) {
  return <div className="v2-container v2-page"><AccountNav active="applications" /><PageHeading eyebrow="Your community activity" title="Event application"><Link href="/applications">← All applications</Link></PageHeading><RequireAccount next={`/applications/events/${id}`}><EventApplicationDetail id={id} /></RequireAccount></div>;
}

function EventApplicationDetail({ id }: { id: string }) {
  const resource = useResource<{ application: Application }>(`applications/${id}/`);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const application = resource.data?.application;
  async function save(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault(); if (!application) return;
    const form = new FormData(event.currentTarget);
    const values: Record<string, unknown> = { cover_letter: form.get('cover_letter') || '' };
    application.event.fields.forEach(field => { values[`field_${field.id}`] = field.field_type === 'boolean' ? form.has(`field_${field.id}`) : form.get(`field_${field.id}`); });
    setBusy(true); setError(null); setMessage('');
    try { await mutate(`applications/${id}/`, values); setMessage('Your application has been updated.'); resource.reload(); }
    catch (cause) { setError(cause as Error); } finally { setBusy(false); }
  }
  return <><ErrorNotice error={resource.error} retry={resource.reload} /><ErrorNotice error={error} />{message && <Notice>{message}</Notice>}{resource.loading && <Loading />}{application && <section className="v2-panel"><div className="v2-section-heading"><h2>{application.event.title}</h2><span className="v2-pill">{application.status}</span></div><p className="v2-small v2-muted">Applied {dateLabel(application.applied_date)} · Deadline {dateLabel(application.event.deadline)}</p>{!application.can_edit && <Notice>This application is available to view. Changes are closed.</Notice>}<form key={application.updated_date} className="v2-form" onSubmit={save}><fieldset disabled={busy || !application.can_edit}>{application.event.fields.map(field => {
    const answer = application.responses.find(response => response.field_id === field.id)?.value;
    return field.field_type === 'boolean' ? <label className="v2-checkbox-row" key={field.id}><input type="checkbox" name={`field_${field.id}`} defaultChecked={answer === true} /><span>{field.name}</span></label> : <Field key={field.id} label={field.name}><input name={`field_${field.id}`} type={['date', 'number'].includes(field.field_type) ? field.field_type : 'text'} step={field.field_type === 'number' ? 'any' : undefined} required={field.required} defaultValue={String(answer ?? '')} /></Field>;
  })}<Field label="Additional message"><textarea name="cover_letter" defaultValue={application.cover_letter} rows={5} maxLength={10000} /></Field>{application.can_edit && <button className="v2-button" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>}</fieldset></form><p><Link className="v2-arrow-link" href={`/events/${application.event.id}`}>View event →</Link></p></section>}</>;
}

type EarlierEdit = { id: number; title: string; description: string; video_url: string; platform: string; status: string; submitted_at: string; deadline: string; upvotes: number; can_edit: boolean; can_confirm: boolean; url: string };

export function EarlierEditsPage({ id }: { id?: string }) {
  return <div className="v2-container v2-page"><AccountNav active="league" /><PageHeading eyebrow="Your creative history" title={id ? 'Earlier submission' : 'Earlier edits'}><p>Your submissions from before the V2 league. New competitions and official points are in the <Link href="/editing-hub">Editing Hub</Link>.</p></PageHeading><RequireAccount next={id ? `/account/edits/${id}` : '/account/edits'}>{id ? <EarlierEditDetail id={id} /> : <EarlierEditList />}</RequireAccount></div>;
}

function EarlierEditList() {
  const [page, setPage] = useState(1);
  const resource = useResource<PageResult<EarlierEdit>>(`member/edits/?page=${page}`);
  return <><ErrorNotice error={resource.error} retry={resource.reload} />{resource.loading && <Loading />}{resource.data && <>{resource.data.results.length ? <div className="v2-two-columns">{resource.data.results.map(edit => <article className="v2-panel" key={edit.id}><div className="v2-meta"><span>{edit.platform}</span><span className="v2-pill">{edit.status}</span></div><h2>{edit.title || 'Untitled edit'}</h2><p className="v2-small v2-muted">Submitted {dateLabel(edit.submitted_at)} · {edit.upvotes} upvotes</p><p>{edit.description}</p><Link href={edit.url} className="v2-arrow-link">{edit.can_edit ? 'Manage submission' : 'View submission'} →</Link></article>)}</div> : <Empty title="No earlier submissions"><Link href="/editing-hub">Find your first league competition →</Link></Empty>}<Pagination page={resource.data.page} pages={resource.data.pages} onPage={setPage} /></>}</>;
}

function EarlierEditDetail({ id }: { id: string }) {
  const resource = useResource<{ edit: EarlierEdit }>(`member/edits/${id}/`);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(false);
  const [withdrawn, setWithdrawn] = useState(false);
  async function act(values: Record<string, unknown>) {
    setBusy(true); setError(null); setMessage('');
    try { const result = await mutate<{ withdrawn?: boolean }>(`member/edits/${id}/`, values); if (result.withdrawn) setWithdrawn(true); else { setMessage(values.operation === 'confirm' ? 'Submission confirmed.' : 'Your edit has been updated.'); resource.reload(); } }
    catch (cause) { setError(cause as Error); } finally { setBusy(false); }
  }
  const edit = resource.data?.edit;
  if (withdrawn) return <Notice>Submission withdrawn. <Link href="/account/edits">Return to your earlier edits →</Link></Notice>;
  return <><Link href="/account/edits" className="v2-back-link">← Earlier edits</Link><ErrorNotice error={resource.error} retry={resource.reload} /><ErrorNotice error={error} />{message && <Notice>{message}</Notice>}{resource.loading && <Loading />}{edit && <section className="v2-panel"><div className="v2-section-heading"><h2>{edit.title || 'Untitled edit'}</h2><span className="v2-pill">{edit.status}</span></div><p className="v2-small v2-muted">Submitted {dateLabel(edit.submitted_at)} · {edit.upvotes} upvotes</p><p><a href={safeUrl(edit.video_url)} target="_blank" rel="noopener noreferrer" className="v2-arrow-link">Watch original edit ↗</a></p>{!edit.can_edit ? <><p>{edit.description}</p><Notice>This historical submission is locked. Its original entry deadline was {dateLabel(edit.deadline)}.</Notice></> : <><form className="v2-form" onSubmit={event => { event.preventDefault(); void act({ ...Object.fromEntries(new FormData(event.currentTarget)), operation: 'save' }); }}><fieldset disabled={busy}><Field label="Title"><input name="title" defaultValue={edit.title} maxLength={200} /></Field><Field label="Video URL"><input name="video_url" type="url" defaultValue={edit.video_url} required maxLength={500} /></Field><Field label="Description"><textarea name="description" defaultValue={edit.description} maxLength={10000} rows={4} /></Field><button className="v2-button" disabled={busy}>Save changes</button></fieldset></form>{edit.can_confirm && <form className="v2-form" onSubmit={event => { event.preventDefault(); void act({ operation: 'confirm', owns_edit: true }); }}><label className="v2-checkbox-row"><input type="checkbox" required disabled={busy} /><span>I confirm that this is my edit and belongs to my approved channel.</span></label><button className="v2-button secondary" disabled={busy}>Confirm submission</button></form>}<div className="v2-actions"><button className="v2-text-button" disabled={busy} onClick={() => setConfirmation(true)}>Withdraw submission</button></div>{confirmation && <Notice>Withdraw this submission? This removes it from your earlier edits.<div className="v2-actions"><button className="v2-button secondary compact" disabled={busy} onClick={() => setConfirmation(false)}>Keep submission</button><button className="v2-button compact" disabled={busy} onClick={() => act({ operation: 'withdraw' })}>Confirm withdrawal</button></div></Notice>}</>}</section>}</>;
}
