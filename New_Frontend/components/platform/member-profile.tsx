'use client';

import { EditorTitle } from './editor-title';

import { useState, type SubmitEvent } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ApiError, api, mutate, safeUrl, useResource } from '@/lib/api';
import { AccountNav } from './account-nav';
import { RequireAccount } from './auth';
import { useSite } from './site-shell';
import { ErrorNotice, Field, Loading, Notice, PageHeading } from './ui';

type ProfileSummary = {
  member: { display_name: string; username: string; profile_picture: string | null; editor_title: string; editor_title_rarity?: string | null; verified_editor: boolean; verified_platforms: string[] };
  profile: { mode: 'account' | 'channel'; approved_channel_source: string; selected_title_id: number | null; uploaded_picture: string | null };
  channels: { platform: string; name: string; thumbnail: string }[];
  titles: { id: number; name: string; rarity: string; description: string }[];
  max_image_mb: number;
  deletion: { password_required: boolean; recent_login_required: boolean; reauth_url: string };
};

const platformName = (platform: string) => platform === 'youtube' ? 'YouTube' : 'TikTok';

export function MemberProfilePage() {
  return <div className="v2-container v2-page"><AccountNav active="profile" />
    <PageHeading eyebrow="Your community identity" title="Your profile"><p>Choose how you appear across the Editing Hub and community.</p></PageHeading>
    <RequireAccount next="/account/profile"><MemberProfile /></RequireAccount>
  </div>;
}

function MemberProfile() {
  const profile = useResource<ProfileSummary>('member/profile/');
  return <><ErrorNotice error={profile.error} retry={profile.reload} />{profile.loading && <Loading label="Loading your profile…" />}
    {profile.data && <ProfileForm initial={profile.data} />}</>;
}

function ProfileForm({ initial }: { initial: ProfileSummary }) {
  const { refreshSession } = useSite();
  const [data, setData] = useState(initial);
  const [mode, setMode] = useState(initial.profile.mode);
  const [channel, setChannel] = useState(initial.channels.some(item => item.platform === initial.profile.approved_channel_source) ? initial.profile.approved_channel_source : '');
  const [titleId, setTitleId] = useState(String(initial.profile.selected_title_id || ''));
  const [removePicture, setRemovePicture] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const selectedTitle = data.titles.find(title => String(title.id) === titleId);

  async function save(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    const upload = body.get('profile_picture');
    setError(null); setMessage('');
    if (upload instanceof File && upload.size > data.max_image_mb * 1024 * 1024) {
      setError(new Error(`Choose an image smaller than ${data.max_image_mb} MB.`)); return;
    }
    if (!(upload instanceof File) || !upload.size) body.delete('profile_picture');
    body.set('approved_channel_source', mode === 'channel' ? channel : '');
    body.set('remove_picture', String(removePicture));
    setBusy(true);
    try {
      const result = await api<ProfileSummary>('member/profile/', { method: 'POST', body });
      setData(result); setMode(result.profile.mode); setChannel(result.profile.approved_channel_source);
      setTitleId(String(result.profile.selected_title_id || '')); setRemovePicture(false);
      const input = form.elements.namedItem('profile_picture');
      if (input instanceof HTMLInputElement) input.value = '';
      await refreshSession();
      setMessage('Your profile has been saved.');
    } catch (error) { setError(error as Error); } finally { setBusy(false); }
  }

  return <div className="v2-settings-grid">
    <aside className="v2-panel">
      <div className="v2-account-avatar">{safeUrl(data.member.profile_picture, '') ? <Image src={safeUrl(data.member.profile_picture)} width={70} height={70} alt="" unoptimized /> : data.member.display_name.slice(0, 1).toUpperCase()}</div>
      <h2>{data.member.display_name}</h2><p className="v2-muted">@{data.member.username}</p><p><EditorTitle name={data.member.editor_title} rarity={data.member.editor_title_rarity} /></p>
      {data.member.verified_editor && <span className="v2-pill">Verified editor</span>}
      {data.member.verified_platforms.length > 0 && <p className="v2-small v2-muted">Verified channels: {data.member.verified_platforms.map(platformName).join(' · ')}</p>}
      <nav className="v2-account-links" aria-label="Profile shortcuts"><Link href="/account/settings">Username & sign-in settings →</Link><Link href="/account/preferences">Email & notification preferences →</Link><Link href="/applications">Your applications →</Link><Link href="/account">Back to dashboard →</Link></nav>
    </aside>
    <div className="v2-stack">
      <section className="v2-panel"><h2>Make it yours</h2>
        <ErrorNotice error={error} />{message && <Notice>{message}</Notice>}
        <form className="v2-form" onSubmit={save}><fieldset disabled={busy}>
          <Field label="Display identity"><select name="profile_display_mode" value={mode} onChange={event => setMode(event.target.value as 'account' | 'channel')}><option value="account">Account username</option><option value="channel" disabled={!data.channels.length}>Approved channel</option></select></Field>
          {mode === 'channel' && <Field label="Approved channel"><select name="approved_channel_source" value={channel} onChange={event => setChannel(event.target.value)} required><option value="">Choose a channel</option>{data.channels.map(item => <option value={item.platform} key={item.platform}>{platformName(item.platform)} · {item.name}</option>)}</select></Field>}
          <p className="v2-small v2-muted">{data.channels.length ? 'Choose your account username or the name of one of your approved, verified channels.' : <>Your account username is your public name. <Link href="/editing-hub/apply">Apply to become an editor</Link> to use an approved channel.</>}</p>
          <Field label="Profile picture"><input type="file" name="profile_picture" accept="image/jpeg,image/png,image/webp" disabled={removePicture} /></Field>
          <p className="v2-small v2-muted">JPEG, PNG or WebP, up to {data.max_image_mb} MB and 4096 × 4096 pixels. Your uploaded picture takes priority over your channel image.</p>
          {data.profile.uploaded_picture && <label className="v2-toggle-row"><span>Remove my uploaded picture</span><input type="checkbox" checked={removePicture} onChange={event => setRemovePicture(event.target.checked)} /></label>}
          {removePicture && <p className="v2-small v2-muted">After saving, your selected channel image or account initial will be shown.</p>}
          <div id="editor-title" className="v2-title-picker"><Field label="Editor title"><select name="selected_title_id" value={titleId} onChange={event => setTitleId(event.target.value)}><option value="">Default community title</option>{data.titles.map(title => <option key={title.id} value={title.id}>{title.name} · {title.rarity}</option>)}</select></Field>
          {selectedTitle && <p className="v2-title-preview"><EditorTitle name={selectedTitle.name} rarity={selectedTitle.rarity} /></p>}
          <p className="v2-small v2-muted">{selectedTitle?.description || (data.titles.length ? 'Choose an unlocked title to show as a badge below your name in the editors table. This does not change league points or ranking.' : 'Your unlocked editor titles will appear here.')}</p>
          </div><button className="v2-button" type="submit">{busy ? 'Saving…' : 'Save profile'}</button>
        </fieldset></form>
      </section>
      <DeleteAccount deletion={data.deletion} />
    </div>
  </div>;
}

function DeleteAccount({ deletion }: { deletion: ProfileSummary['deletion'] }) {
  const [opened, setOpened] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  async function remove(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      await mutate('member/profile/delete/', Object.fromEntries(new FormData(event.currentTarget)));
      window.location.assign('/');
    } catch (error) { setError(error as Error); setBusy(false); }
  }
  return <section className="v2-panel"><h2>Account removal</h2><p className="v2-muted">Deleting your account permanently removes your sign-in and personal account data. Orders and official community records may require a support review before removal.</p>
    {!opened ? <button className="v2-button secondary" type="button" onClick={() => setOpened(true)}>Request account deletion</button> : <>
      <ErrorNotice error={error} />
      {error instanceof ApiError && error.code === 'protected_records' && <p><Link href="/contact">Contact support about account removal →</Link></p>}
      <form className="v2-form" onSubmit={remove}><fieldset disabled={busy}>
        <p>This action cannot be undone. Type DELETE to confirm.</p>
        <Field label="Deletion confirmation"><input name="confirmation" value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="off" required pattern="DELETE" /></Field>
        {deletion.password_required ? <Field label="Current password"><input name="password" type="password" autoComplete="current-password" required /></Field> : <p className="v2-small v2-muted">For your security, Google sign-in must have been completed within the last 10 minutes. <Link href={deletion.reauth_url}>Sign in again</Link>, then return to confirm deletion.</p>}
        <div className="v2-actions"><button type="submit" className="v2-button" disabled={busy || confirmation !== 'DELETE'}>{busy ? 'Deleting…' : 'Permanently delete account'}</button><button type="button" className="v2-button secondary" onClick={() => { setOpened(false); setConfirmation(''); setError(null); }}>Keep my account</button></div>
      </fieldset></form>
    </>}
  </section>;
}
