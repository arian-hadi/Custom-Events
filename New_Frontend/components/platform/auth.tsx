'use client';

import { useState, type FormEvent, type ReactNode } from 'react';
import { ApiError, mutate, safeUrl, useResource, type Session } from '@/lib/api';
import { useSite } from './site-shell';
import { AuthArt } from './auth-art';
import { AccountNav } from './account-nav';
import { Captcha, ErrorNotice, Field, Loading, Notice, PageHeading } from './ui';

export type AuthMode = 'login' | 'register' | 'verify-email' | 'forgot-password' | 'reset-password';
export type Query = Record<string, string | string[] | undefined>;
function queryValue(query: Query, name: string) { return typeof query[name] === 'string' ? query[name] as string : ''; }
function localDestination(value: string) { return value.startsWith('/') && !value.startsWith('//') && !value.includes('\\') && !/[\u0000-\u0020]/.test(value) ? value : '/account'; }
const googleErrors: Record<string, string> = { google_failed: 'Google sign-in could not be completed. Please try again.', google_account_exists: 'An account already uses this email. Sign in with your password, then link Google from your account.', google_disabled: 'Google sign-in is not currently available.', google_link_failed: 'Google could not be linked to this account. Please try again.', google_email_unavailable: 'Your account was created, but its verification email could not be sent. Please visit email verification to request a new code.' };

export function RequireAccount({ children, next }: { children: ReactNode; next?: string }) {
  const { user, sessionLoading, sessionError } = useSite();
  if (sessionLoading) return <Loading label="Checking your account…" />;
  if (sessionError) return <ErrorNotice error={sessionError} retry={() => window.location.reload()} />;
  if (!user) return <Notice>Please <a href={next ? `/login?next=${encodeURIComponent(next)}` : '/login'}>sign in</a> to continue.</Notice>;
  return <>{children}</>;
}

export function AuthPage({ mode, query = {} }: { mode: AuthMode; query?: Query }) {
  const { session, sessionError, refreshSession, site, siteLoading } = useSite();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const [completed, setCompleted] = useState(false);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [email, setEmail] = useState(queryValue(query, 'email'));
  const [captchaToken, setCaptchaToken] = useState('');
  const [captchaReset, setCaptchaReset] = useState(0);
  const [resending, setResending] = useState(false);
  const requiresCaptcha = ['register', 'forgot-password'].includes(mode);
  const siteKey = requiresCaptcha ? session?.recaptcha_site_key || '' : '';
  const titles: Record<AuthMode, string> = { login: 'Welcome back', register: 'Join the community', 'verify-email': 'Verify your email', 'forgot-password': 'Forgot your password?', 'reset-password': 'Choose a new password' };
  const subtitles: Record<AuthMode, string> = { login: 'Sign in to make yourself at home.', register: 'Create your account and start exploring.', 'verify-email': 'Enter the verification code sent to your email.', 'forgot-password': 'We’ll send you a link to reset your password.', 'reset-password': 'Use a strong password you don’t use elsewhere.' };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setMessage(''); setNeedsVerification(false);
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(form.entries());
    if (siteKey) body.recaptcha_token = captchaToken;
    try {
      if (mode === 'login') { await mutate<Session>('auth/login/', body); await refreshSession(); window.location.assign(localDestination(queryValue(query, 'next'))); }
      if (mode === 'register') { const result = await mutate<{ email: string }>('auth/register/', body); window.location.assign(`/verify-email?email=${encodeURIComponent(result.email || email)}`); }
      if (mode === 'verify-email') { await mutate('auth/verify-email/', body); await refreshSession(); setCompleted(true); setMessage('Your email has been verified. You can continue to your account.'); }
      if (mode === 'forgot-password') { const result = await mutate<{ detail: string }>('auth/password-reset/', body); setMessage(result.detail || 'If an account exists for this address, you’ll receive a reset link.'); }
      if (mode === 'reset-password') { await mutate('auth/password-reset-confirm/', { ...body, uid: queryValue(query, 'uid'), token: queryValue(query, 'token') }); setCompleted(true); setMessage('Your password has been updated. Sign in with your new password.'); }
    } catch (error) {
      setError(error as Error);
      if (error instanceof ApiError && ['verification_required', 'email_unavailable'].includes(error.code)) setNeedsVerification(true);
    } finally { setBusy(false); setCaptchaReset(value => value + 1); }
  }
  async function resend() {
    setResending(true); setError(null); setMessage('');
    try { const result = await mutate<{ detail: string }>('auth/resend-verification/', { email, recaptcha_token: captchaToken }); setMessage(result.detail || 'If your account needs verification, a new code has been sent.'); }
    catch (error) { setError(error as Error); }
    finally { setResending(false); setCaptchaReset(value => value + 1); }
  }
  return <div className="v2-container v2-page v2-auth-page"><AuthArt site={site} loading={siteLoading} /><div className="v2-auth-panel"><PageHeading eyebrow="Your community account" title={titles[mode]}><p>{subtitles[mode]}</p></PageHeading><ErrorNotice error={sessionError} /><ErrorNotice error={error} />{queryValue(query, 'error') && googleErrors[queryValue(query, 'error')] && <Notice error>{googleErrors[queryValue(query, 'error')]}</Notice>}{message && <Notice>{message}{completed && mode === 'verify-email' && <p><a href="/account">Continue to account →</a></p>}{mode === 'reset-password' && <p><a href="/login">Sign in →</a></p>}</Notice>}{needsVerification && <p><a href={`/verify-email?email=${encodeURIComponent(email)}`}>Verify your email to continue →</a></p>}
    {!completed && <form onSubmit={submit} className="v2-form"><fieldset disabled={busy || resending}>
      {mode === 'register' && <Field label="Username"><input name="username" autoComplete="username" required maxLength={150} /></Field>}
      {mode === 'verify-email' && queryValue(query, 'email') ? <><input type="hidden" name="email" value={email} /><p>Enter the code for <strong>{email}</strong>. Check your inbox and spam folder.</p></> : ['login', 'register', 'verify-email', 'forgot-password'].includes(mode) && <Field label="Email address"><input type="email" name="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} /></Field>}
      {mode === 'login' && <Field label="Password"><input name="password" type="password" autoComplete="current-password" required /></Field>}
      {mode === 'register' && <><Field label="Password"><input name="password1" type="password" autoComplete="new-password" required minLength={8} /></Field><Field label="Confirm password"><input name="password2" type="password" autoComplete="new-password" required minLength={8} /></Field><p className="v2-small v2-muted">Use at least 8 characters. Avoid common passwords and personal information.</p></>}
      {mode === 'verify-email' && <Field label="Verification code"><input name="code" autoComplete="one-time-code" required inputMode="numeric" /></Field>}
      {mode === 'reset-password' && <><Field label="New password"><input name="new_password1" type="password" autoComplete="new-password" required minLength={8} /></Field><Field label="Confirm new password"><input name="new_password2" type="password" autoComplete="new-password" required minLength={8} /></Field></>}
      <Captcha siteKey={siteKey} onToken={setCaptchaToken} resetKey={captchaReset} />
      {mode === 'register' && <p className="v2-small v2-muted">By creating an account, you agree to our <a href="/terms/">terms</a> and <a href="/privacy/">privacy policy</a>.</p>}
      <button className="v2-button full-width" type="submit" disabled={busy || Boolean(siteKey && !captchaToken)}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in →' : mode === 'register' ? 'Create account →' : mode === 'verify-email' ? 'Verify email →' : mode === 'forgot-password' ? 'Send reset link →' : 'Update password →'}</button>
    </fieldset></form>}
    {['login', 'register'].includes(mode) && session?.google_enabled && <><div className="v2-divider"><span>or</span></div><a href="/api/v2/auth/google/start/" className="v2-button secondary full-width"><span className="v2-google-g" aria-hidden="true">G</span> Continue with Google</a></>}
    {mode === 'verify-email' && !completed && <div className="v2-resend"><p className="v2-small v2-muted">Your first code is sent when you create your account. Only request another if it hasn’t arrived or has expired.</p><Captcha siteKey={session?.recaptcha_site_key || ''} onToken={setCaptchaToken} resetKey={captchaReset} /><button type="button" className="v2-text-button" onClick={resend} disabled={busy || resending || !email || Boolean(session?.recaptcha_site_key && !captchaToken)}>{resending ? 'Sending…' : 'Resend code'}</button></div>}
    <div className="v2-auth-links">{mode === 'login' ? <><a href="/forgot-password">Forgot password?</a><span>New here? <a href="/register">Create an account</a></span></> : <a href="/login">← Back to sign in</a>}</div></div></div>;
}

export function AccountSettingsPage({ query = {} }: { query?: Query }) {
  const error = googleErrors[queryValue(query, 'error')];
  return <div className="v2-container v2-page"><AccountNav active="settings" /><PageHeading eyebrow="Your account" title="Account settings"><p>Manage your sign-in details and the way you connect.</p></PageHeading>{error && <Notice error>{error}</Notice>}<RequireAccount><AccountSettings /></RequireAccount></div>;
}
function AccountSettings() {
  const { user, session, refreshSession } = useSite();
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>, password = false) {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setError(null); setMessage('');
    try { await mutate(password ? 'auth/password-change/' : 'auth/profile/', Object.fromEntries(new FormData(form)), password ? 'POST' : 'PATCH'); await refreshSession(); setMessage(password ? 'Your password has been changed.' : 'Your profile has been saved.'); if (password) form.reset(); }
    catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  async function linkGoogle() {
    setBusy(true); setError(null);
    try { const result = await mutate<{ authorization_url: string }>('auth/google/link/'); const url = safeUrl(result.authorization_url, ''); if (!url) throw new Error('Google sign-in could not be started.'); window.location.assign(url); }
    catch (error) { setError(error as Error); setBusy(false); }
  }
  return <><ErrorNotice error={error} />{message && <Notice>{message}</Notice>}<div className="v2-settings-grid"><aside className="v2-panel"><div className="v2-account-avatar">{safeUrl(user?.profile_picture, '') ? <img src={safeUrl(user?.profile_picture)} alt="" /> : user?.username.slice(0, 1).toUpperCase()}</div><h2>{user?.username}</h2><p className="v2-muted">{user?.email}</p><nav className="v2-account-links"><a href="/account/preferences">Notification preferences →</a><a href="/notifications">Notifications →</a><a href="/favorites">Saved products →</a><a href="/account/orders">Your orders →</a><a href="/applications">Your applications →</a><a href="/account">Dashboard →</a><a href="/account/profile">Your profile →</a>{user?.is_staff && <a href="/admin/">Administration ↗</a>}</nav></aside><div className="v2-stack"><section className="v2-panel"><h2>Profile</h2><form className="v2-form" onSubmit={event => save(event)}><Field label="Username"><input name="username" defaultValue={user?.username} required maxLength={150} autoComplete="username" /></Field><Field label="Email address"><input type="email" value={user?.email || ''} readOnly /></Field><p className="v2-small v2-muted">Your email is tied to your verified account. Contact us if it needs to change.</p><button className="v2-button" disabled={busy}>Save profile</button></form></section><section className="v2-panel"><h2>Connected accounts</h2><p className="v2-muted">{user?.google_linked ? 'Your Google account is connected.' : 'Use Google to sign in to this account.'}</p>{user?.google_linked ? <span className="v2-pill">Google connected ✓</span> : session?.google_enabled ? <button className="v2-button secondary" disabled={busy} onClick={linkGoogle}>Connect Google</button> : <p className="v2-small v2-muted">Google sign-in is not available yet.</p>}</section><section className="v2-panel"><h2>{user?.has_password ? 'Change password' : 'Set a password'}</h2>{user?.has_password ? <form className="v2-form" onSubmit={event => save(event, true)}><Field label="Current password"><input name="old_password" type="password" autoComplete="current-password" required /></Field><Field label="New password"><input name="new_password1" type="password" autoComplete="new-password" required minLength={8} /></Field><Field label="Confirm new password"><input name="new_password2" type="password" autoComplete="new-password" required minLength={8} /></Field><button className="v2-button" disabled={busy}>Update password</button></form> : <p>Use <a href="/forgot-password">password recovery</a> to create a password for this account.</p>}</section></div></div></>;
}

const preferenceLabels: Record<string, string> = {
  email_notifications: 'Email notifications', in_app_notifications: 'In-app notifications',
  email_enabled: 'Allow optional emails (master switch)', in_app_enabled: 'In-app notifications',
  email_newsletter: 'Newsletters and community announcements', email_blog_updates: 'New blog posts', email_shop_updates: 'New shop products',
  email_application_updates: 'Application decisions', email_ranking_updates: 'Official league standing updates',
  email_edit_reports: 'Edit verification and league results', email_achievements: 'Editor titles and league awards',
};
function preferenceLabel(name: string) { return preferenceLabels[name] || name.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase()); }
export function PreferencesPage() { return <div className="v2-container v2-page"><AccountNav active="preferences" /><PageHeading eyebrow="Your choice" title="Notification preferences"><p>Choose which updates you want to receive.</p></PageHeading><RequireAccount><PreferencesForm /></RequireAccount></div>; }
function PreferencesForm() {
  const preferences = useResource<{ preferences: Record<string, boolean>; email_activity_delivery_active: boolean; email_activity_capture_mode: boolean; email_campaign_delivery_active: boolean; email_campaign_capture_mode: boolean }>('notification-preferences/');
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setMessage(''); setBusy(true);
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(Object.entries(preferences.data?.preferences || {}).filter(([, value]) => typeof value === 'boolean').map(([key]) => [key, form.has(key)]));
    try { await mutate('notification-preferences/', values, 'PATCH'); setMessage('Your notification preferences have been saved.'); }
    catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  return <div className="v2-narrow">
    <ErrorNotice error={preferences.error} retry={preferences.reload} /><ErrorNotice error={error} />
    {message && <Notice>{message}</Notice>}{preferences.loading && <Loading />}
    {preferences.data && <>
      <p>Turn off the email master switch to stop optional emails, or choose the topics you want below. Optional member emails include an unsubscribe link. Account security emails and order receipts are separate.</p>
      {!preferences.data.email_campaign_delivery_active && !preferences.data.email_campaign_capture_mode && <Notice>Campaign delivery is currently paused. You can still save your choices.</Notice>}
      {preferences.data.email_campaign_capture_mode && <Notice>This preview captures campaign emails locally; it does not deliver them to inboxes.</Notice>}
      {preferences.data.email_activity_capture_mode ? <Notice>This preview captures activity emails locally; it does not deliver them to inboxes.</Notice>
        : !preferences.data.email_activity_delivery_active ? <Notice>Activity email delivery is currently paused. Your preferences will apply when delivery resumes.</Notice>
          : <p className="v2-small v2-muted">Application decisions, official league updates, edit results and achievements can be emailed according to your choices below.</p>}
      <form className="v2-panel v2-form" onSubmit={save}>
        {Object.entries(preferences.data.preferences).filter(([, value]) => typeof value === 'boolean').map(([key, value]) => <label key={key} className="v2-toggle-row"><span>{preferenceLabel(key)}</span><input type="checkbox" name={key} defaultChecked={value} disabled={busy} role="switch" /></label>)}
        <button className="v2-button" disabled={busy}>{busy ? 'Saving…' : 'Save preferences'}</button>
      </form>
    </>}
  </div>;
}


