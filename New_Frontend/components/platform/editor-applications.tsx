'use client';

/* oxlint-disable next/no-html-link-for-pages -- The native admin link opens Django, outside the Next.js router. */

import { useState, type SubmitEvent } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react';
import { api, dateLabel, mutate, safeUrl, useResource } from '@/lib/api';
import { AccountNav } from './account-nav';
import { RequireAccount } from './auth';
import { ErrorNotice, Field, Loading, Notice, PageHeading } from './ui';

type Choice = { value: string; label: string };
type EditorApplication = {
  id: number; platform: string; channel_link: string; channel_name: string;
  channel_thumbnail: string; channel_screenshot: string | null;
  editing_area: string; editing_area_label: string; editing_area_other: string;
  editing_tool_label: string; status: string; channel_verified: boolean;
  removal_requested: boolean; applied_at: string; reviewed_at: string | null;
  can_confirm: boolean; can_remove: boolean; url: string;
};
type ApplicationOptions = {
  results: EditorApplication[]; can_apply: boolean; platforms: Choice[];
  editing_areas: Choice[]; editing_tools: Choice[]; max_screenshot_mb: number;
};

export function editorApplicationStatus(item: EditorApplication) {
  if (item.removal_requested) return 'Removal requested';
  if (item.can_confirm) return item.status === 'accepted' ? 'Approved — confirm your channel' : 'Confirm your channel';
  return ({ pending: 'Under review', accepted: 'Approved', rejected: 'Not approved' })[item.status] || item.status;
}

export function EditorApplyPage({ initialPlatform = 'youtube' }: { initialPlatform?: string }) {
  const platform = initialPlatform === 'tiktok' ? 'tiktok' : 'youtube';
  return <div className="v2-container v2-page v2-editor-page">
    <AccountNav active="applications" />
    <PageHeading eyebrow="Your place in the community" title="Become an editor">
      <p>Connect your channel, show us your work, and join the creator community.</p>
    </PageHeading>
    <RequireAccount next={`/editing-hub/apply?platform=${platform}`}><EditorApplyForm initialPlatform={platform} /></RequireAccount>
  </div>;
}

function EditorApplyForm({ initialPlatform }: { initialPlatform: string }) {
  const options = useResource<ApplicationOptions>('editor-applications/');
  const [platform, setPlatform] = useState(initialPlatform);
  const [area, setArea] = useState('transformers');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const active = options.data?.results.find(item => ['pending', 'accepted'].includes(item.status) && !item.removal_requested);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = new FormData(event.currentTarget);
    const screenshot = body.get('channel_screenshot');
    setError(null);
    if (screenshot instanceof File && screenshot.size > (options.data?.max_screenshot_mb || 4) * 1024 * 1024) {
      setError(new Error(`Choose an image smaller than ${options.data?.max_screenshot_mb} MB.`)); return;
    }
    setBusy(true);
    try {
      const result = await api<{ application: EditorApplication }>('editor-applications/', { method: 'POST', body, signal: AbortSignal.timeout(120000) });
      window.location.assign(`/applications/editors/${result.application.id}`);
    } catch (error) { setError(error as Error); setBusy(false); }
  }

  return <><ErrorNotice error={options.error} retry={options.reload} />{options.loading && <Loading label="Loading your editor applications…" />}
    {options.data && (!options.data.can_apply ? <Notice>Editor applications are for normal member accounts. Use a member account to apply, or <a href="/admin/edithub/editorapplication/">review applications in administration</a>.</Notice> : <div className="v2-editor-layout">
      <section className="v2-panel" aria-labelledby="editor-channel-title">
        <span className="v2-eyebrow">01 · Your channel</span><h2 id="editor-channel-title">Introduce your work</h2>
        <p className="v2-muted">Choose one channel: YouTube or TikTok. You can have one active editor application.</p>
        <ErrorNotice error={error} />
        <form className="v2-form" onSubmit={submit}><fieldset disabled={busy}>
          {active ? <Notice><strong>{editorApplicationStatus(active)}</strong><p>You already have a {active.platform === 'youtube' ? 'YouTube' : 'TikTok'} application. Continue with this channel; a second platform application is not needed.</p><Link className="v2-arrow-link" href={`/applications/editors/${active.id}`}>{active.can_confirm ? 'Continue your application' : 'View your application'} →</Link></Notice> : <>
            <Field label="Platform"><select name="channel_type" value={platform} onChange={event => { setPlatform(event.target.value); setError(null); }}>{options.data.platforms.map(choice => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></Field>
            <Field label="Channel URL"><input name="channel_link" type="url" required maxLength={500} placeholder={`https://www.${platform}.com/@yourchannel`} autoComplete="url" /></Field>
            <div className="v2-form-row">
              <Field label="Editing area"><select name="editing_area" value={area} onChange={event => setArea(event.target.value)}>{options.data.editing_areas.map(choice => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></Field>
              <Field label="Primary editing software"><select name="editing_tool" defaultValue="after_effects">{options.data.editing_tools.map(choice => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select></Field>
            </div>
            {area === 'others' && <Field label="Your editing area"><input name="editing_area_other" required maxLength={200} /></Field>}
            <Field label="Channel ownership screenshot"><input name="channel_screenshot" type="file" accept="image/png,image/jpeg,image/webp" required aria-describedby="editor-upload-help" /></Field>
            <p id="editor-upload-help" className="v2-small v2-muted">Upload a screenshot showing that you manage this channel. PNG, JPEG or WebP, up to {options.data.max_screenshot_mb} MB.</p>
            <label className="v2-checkbox-row"><input name="data_consent" type="checkbox" required /><span>I consent to my channel information being displayed on this website and confirm I have the right to submit it.</span></label>
            <button className="v2-button" type="submit" disabled={busy}>{busy ? 'Loading your channel…' : 'Review your channel'}<ArrowRight size={17} aria-hidden="true" /></button>
            {busy && <output className="v2-small v2-muted">Channel lookup can take a moment. Keep this page open.</output>}
          </>}
        </fieldset></form>
      </section>
      <aside className="v2-stack">
        <section className="v2-panel v2-editor-guide"><ShieldCheck size={28} aria-hidden="true" /><h2>From creator to editor</h2>
          <ol><li><strong>Connect your channel</strong><span>Share your profile and an ownership screenshot.</span></li><li><strong>Check and confirm</strong><span>Review the channel we find and confirm it belongs to you.</span></li><li><strong>Admin review</strong><span>We’ll review your application. Follow its status in your dashboard.</span></li></ol>
          <p className="v2-small v2-muted">Editor applications are open even when competition entries are closed. Approval and your channel confirmation let you enter when a league round opens.</p>
        </section>
        <section className="v2-panel"><h2>Your applications</h2>{options.data.results.length ? <ul className="v2-editor-history">{options.data.results.map(item => <li key={item.id}><Link href={`/applications/editors/${item.id}`}><strong>{item.channel_name || item.platform}</strong><span>{editorApplicationStatus(item)}</span></Link></li>)}</ul> : <p className="v2-muted">Your first application starts here.</p>}<Link className="v2-arrow-link" href="/applications">All applications →</Link></section>
      </aside>
    </div>)}
  </>;
}

export function EditorApplicationPage({ id }: { id: string }) {
  return <div className="v2-container v2-page v2-editor-page"><AccountNav active="applications" />
    <PageHeading eyebrow="Your creator journey" title="Editor application"><p><Link href="/applications">← All applications</Link></p></PageHeading>
    <RequireAccount next={`/applications/editors/${id}`}><EditorApplicationDetail id={id} /></RequireAccount>
  </div>;
}

function EditorApplicationDetail({ id }: { id: string }) {
  const resource = useResource<{ application: EditorApplication }>(`editor-applications/${id}/`);
  const item = resource.data?.application;
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [confirmation, setConfirmation] = useState<'cancel' | 'remove' | null>(null);
  async function act(operation: 'confirm' | 'cancel' | 'remove') {
    setBusy(true); setError(null); setMessage('');
    try {
      await mutate(`editor-applications/${id}/${operation}/`, operation === 'confirm' ? { owns_channel: true } : {});
      if (operation === 'cancel') { window.location.assign('/editing-hub/apply'); return; }
      setMessage(operation === 'confirm' ? (item?.status === 'accepted' ? 'Channel confirmed. Your approval is unchanged; you can now submit your league entry.' : 'Application submitted for admin review. You can follow its status here or in your dashboard.') : 'Your removal request has been submitted for admin review.');
      setConfirmation(null); resource.reload();
    } catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  return <><ErrorNotice error={resource.error} retry={resource.reload} /><ErrorNotice error={error} />{message && <Notice>{message}</Notice>}{resource.loading && <Loading label="Loading your application…" />}
    {item && <div className="v2-editor-layout"><section className="v2-panel">
      <div className="v2-editor-identity">{safeUrl(item.channel_thumbnail, '') && <Image unoptimized width={72} height={72} src={safeUrl(item.channel_thumbnail)} alt="" />}<div><span className="v2-eyebrow">{item.platform === 'youtube' ? 'YouTube' : 'TikTok'} editor</span><h2>{item.channel_name || 'Your channel'}</h2><span className="v2-pill">{editorApplicationStatus(item)}</span></div></div>
      <dl className="v2-responses"><div><dt>Channel</dt><dd><a href={safeUrl(item.channel_link)} target="_blank" rel="noopener noreferrer">{item.channel_link} ↗</a></dd></div><div><dt>Editing area</dt><dd>{item.editing_area === 'others' ? item.editing_area_other : item.editing_area_label}</dd></div><div><dt>Software</dt><dd>{item.editing_tool_label}</dd></div><div><dt>Created</dt><dd>{dateLabel(item.applied_at)}</dd></div>{item.reviewed_at && <div><dt>Reviewed</dt><dd>{dateLabel(item.reviewed_at)}</dd></div>}</dl>
      {safeUrl(item.channel_screenshot, '') && <details className="v2-editor-screenshot"><summary>View your ownership screenshot</summary><Image unoptimized width={960} height={540} style={{ width: '100%', height: 'auto' }} src={safeUrl(item.channel_screenshot)} alt="Your submitted channel ownership screenshot" /></details>}
      {item.can_confirm && <form className="v2-form" onSubmit={event => { event.preventDefault(); void act('confirm'); }}><fieldset disabled={busy}><h3>Is this your channel?</h3><p className="v2-muted">{item.status === 'accepted' ? 'Your application is already approved. Confirm that this channel belongs to you to finish setup and enter the league.' : 'Check the details above. Your application will be sent to an admin after you confirm.'}</p><label className="v2-checkbox-row"><input type="checkbox" required /><span>I confirm this channel belongs to me and the information is correct.</span></label><div className="v2-actions"><button className="v2-button" type="submit">{busy ? 'Saving…' : item.status === 'accepted' ? 'Confirm channel & unlock league entry' : 'Confirm & submit application'}</button>{item.status === 'pending' && <button className="v2-text-button" type="button" onClick={() => setConfirmation('cancel')}>Cancel and start again</button>}</div></fieldset></form>}
      {item.can_remove && <button className="v2-text-button" disabled={busy} onClick={() => setConfirmation('remove')}>Request editor removal</button>}
      {confirmation && <Notice>{confirmation === 'cancel' ? 'Cancel this unconfirmed application? You can then submit corrected details.' : 'Request removal of this editor channel? It will stop being available for new league entries while the request is reviewed.'}<div className="v2-actions"><button className="v2-button secondary compact" disabled={busy} onClick={() => setConfirmation(null)}>Keep application</button><button className="v2-button compact" disabled={busy} onClick={() => act(confirmation)}>{busy ? 'Saving…' : confirmation === 'cancel' ? 'Confirm cancellation' : 'Confirm removal request'}</button></div></Notice>}
    </section><aside className="v2-panel v2-editor-guide"><CheckCircle2 size={28} aria-hidden="true" /><h2>{item.can_confirm ? 'One more step' : item.removal_requested ? 'Removal requested' : item.status === 'accepted' ? 'You’re an approved editor' : item.status === 'rejected' ? 'Application reviewed' : 'You’re in the review queue'}</h2><p className="v2-muted">{item.can_confirm ? (item.status === 'accepted' ? 'An admin approved your application before you confirmed channel ownership. Complete that one step here; no new application or review is needed.' : 'Confirm your channel to finish applying. Channel confirmation is your declaration of ownership; an admin still reviews your application.') : item.removal_requested ? 'An admin will review your removal request. You can check its status here.' : item.status === 'accepted' ? 'Visit the Editing Hub to see upcoming rounds and manage your competition entries.' : item.status === 'rejected' ? 'Your application was not approved. Contact us if you need help understanding the next steps.' : 'Your channel is awaiting admin approval. You don’t need to submit it again.'}</p><div className="v2-stack"><Link className="v2-button secondary compact" href="/account">Back to dashboard</Link><Link className="v2-arrow-link" href={item.status === 'rejected' ? '/contact-us' : '/editing-hub#league-entry'}>{item.status === 'rejected' ? 'Contact the team' : item.status === 'accepted' && item.channel_verified && !item.removal_requested ? 'Submit your league edit' : 'View league entry requirements'} →</Link></div></aside></div>}
  </>;
}
