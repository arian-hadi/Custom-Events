import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import Module, { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from 'cheerio';
import ts from 'typescript';

// Compile the real presentation component in memory. Node can strip helper
// types, but TSX needs the TypeScript compiler already installed by Next.js.
// Application code is real; CSS module class names use stable keys because
// Node does not run Next's CSS loader. No build files are written.
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const compiledModules = new Map();
function loadComponent(filename) {
  if (compiledModules.has(filename)) return compiledModules.get(filename).exports;
  const componentModule = new Module(filename);
  componentModule.filename = filename;
  compiledModules.set(filename, componentModule);
  if (filename.endsWith('.module.css')) {
    componentModule.exports = { __esModule: true, default: new Proxy(Object.create(null), {
      get: (_target, key) => typeof key === 'string' ? key : undefined,
    }) };
    return componentModule.exports;
  }
  const packageRequire = createRequire(filename);
  componentModule.require = specifier => {
    if (!specifier.startsWith('.') && !specifier.startsWith('@/')) return packageRequire(specifier);
    const base = specifier.startsWith('@/')
      ? resolve(frontendRoot, specifier.slice(2))
      : resolve(dirname(filename), specifier);
    const dependency = [base, `${base}.ts`, `${base}.tsx`].find(candidate => existsSync(candidate));
    assert.ok(dependency, `Cannot resolve ${specifier} from ${filename}`);
    return loadComponent(dependency);
  };
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  componentModule._compile(compiled.outputText, filename);
  return componentModule.exports;
}
const { applicationStatus, dashboardAttention, submissionDeadline } = loadComponent(resolve(frontendRoot, 'lib/member-dashboard.ts'));

function emptyMember() {
  return {
    generated_at: '2026-10-02T12:00:00Z',
    member: { id: 42, username: 'sample-editor', display_name: 'Sample Editor', profile_picture: null, editor_title: '', verified_editor: false, verified_platforms: [] },
    league: {
      enabled: false, configuration_ready: false, can_submit: false, reason: 'disabled', season: null,
      month: { label: 'October', rank: null, points: null, scored_rounds: 0 },
      season_standing: { rank: null, points: null, scored_rounds: 0 },
      current_week: null, next_week: null, submission_deadline: null, current_entry: null, next_entry: null, latest_result: null, rank_change: null,
    },
    latest_edit: null,
    edit_stats: { league_submissions: 0, legacy_submissions: 0, legacy_verified: 0, legacy_upvotes: 0, league_points: null, best_league_result: null },
    applications: {
      editors: ['youtube', 'tiktok'].map(platform => ({ id: null, platform, status: 'not_applied', channel_name: '', channel_verified: false, removal_requested: false, applied_at: null, updated_at: null, url: `/editor-applications/apply/?platform=${platform}` })),
      events: [], event_count: 0,
    },
    notifications: { unread_count: 0, results: [] }, orders: [], favorites_count: 0,
  };
}

function order(id, status = 'paid') {
  return { id, product_id: 12, product_name: `Collector item ${id}`, display_amount: '29.00', currency: 'usd', status, fulfillment_status: 'pending', fulfillment_note: '', created_at: '2026-10-01T09:00:00Z', paid_at: status === 'paid' ? '2026-10-01T09:01:00Z' : null, url: `/account/orders/${id}` };
}

function activeMember() {
  const data = emptyMember();
  data.member = { ...data.member, profile_picture: 'https://images.example.test/avatar.png', editor_title: 'Community creator', verified_editor: true, verified_platforms: ['youtube'] };
  data.league = {
    ...data.league, enabled: true, configuration_ready: true, can_submit: true, reason: '',
    season: { id: 1, year: 2026, name: '2026 Editing League' },
    month: { label: 'October', rank: 18, points: '1240', scored_rounds: 2 },
    season_standing: { rank: 12, points: '2015', scored_rounds: 5 },
    current_week: { id: 7, label: 'Autobot challenge', starts_at: '2026-09-28T00:00:00Z', cutoff_at: '2026-10-03T00:00:00Z', state: 'active' },
    next_week: { id: 8, label: 'Bumblebee edit challenge', starts_at: '2026-10-05T00:00:00Z', cutoff_at: '2026-10-10T00:00:00Z', state: 'scheduled' },
    submission_deadline: '2026-10-05T12:00:00Z',
    current_entry: { id: 70, title: 'Rise again', state: 'eligible', video_url: 'https://video.example.test/70', detail_url: '/editing-hub#entry-70' },
    latest_result: { entry_id: 60, title: 'Stand together', rank: 7, points: '185', weekly_score: '82.1', period_label: 'September final round', scored_at: '2026-09-27T00:00:00Z', video_url: 'https://video.example.test/60' },
    rank_change: 2,
  };
  data.latest_edit = { id: 70, source: 'league', title: 'Optimus Prime | Rise Again', video_url: 'https://video.example.test/70', thumbnail: 'https://images.example.test/edit.jpg', platform: 'youtube', submitted_at: '2026-09-28T12:00:00Z', state: 'eligible', rank: null, league_points: null, upvotes: null, detail_url: '/editing-hub#entry-70' };
  data.edit_stats = { league_submissions: 6, legacy_submissions: 4, legacy_verified: 3, legacy_upvotes: 94, league_points: '2015', best_league_result: 7 };
  data.applications.editors[0] = { ...data.applications.editors[0], id: 10, status: 'accepted', channel_name: 'Editor Channel', channel_verified: true };
  data.applications.editors[1] = { ...data.applications.editors[1], id: 11, status: 'pending', channel_name: 'TikTok Channel' };
  data.applications.events = [{ id: 8, event_id: 4, title: 'Community showcase', status: 'accepted', applied_at: '2026-09-27T12:00:00Z', updated_at: '2026-10-01T12:00:00Z', url: '/applications/8' }];
  data.applications.event_count = 1;
  data.notifications = { unread_count: 3, results: Array.from({ length: 5 }, (_, index) => ({ id: index + 1, title: `Update ${index + 1}`, message: `Community update ${index + 1}`, is_read: index > 2, created_at: '2026-10-01T12:00:00Z', url: `/notifications#${index + 1}` })) };
  data.orders = [order('1048'), order('1047', 'open')];
  data.favorites_count = 5;
  return data;
}

function renderDashboard(data, props = {}) {
  const { DashboardContent } = loadComponent(resolve(frontendRoot, 'components/platform/member-dashboard.tsx'));
  assert.equal(typeof DashboardContent, 'function', 'The dashboard must expose its actual presentation component');
  return load(renderToStaticMarkup(createElement(DashboardContent, { data, ...props })));
}

test('new members see one editor application invitation, with no second-platform prompts', () => {
  const { EditorApplicationsPanel } = loadComponent(resolve(frontendRoot, 'components/platform/member-dashboard.tsx'));
  for (const editors of [[], emptyMember().applications.editors]) {
    const $ = load(renderToStaticMarkup(createElement(EditorApplicationsPanel, { editors })));
    assert.equal($('a').length, 1);
    assert.equal($('a').attr('href'), '/editing-hub/apply');
    assert.match($.text(), /one YouTube or TikTok channel/);
    assert.doesNotMatch($.text(), /Not applied/);
  }
});

test('application statuses use the same member-facing meanings across both application systems', () => {
  assert.equal(applicationStatus('accepted'), 'Approved');
  assert.equal(applicationStatus('approved'), 'Approved');
  assert.equal(applicationStatus('pending'), 'Under review');
  assert.equal(applicationStatus('not_applied'), 'Not applied');
  assert.equal(applicationStatus('rejected'), 'Rejected');
  assert.equal(applicationStatus('withdrawn'), 'Withdrawn');
});

test('deadline labels handle boundaries, missing dates and singular units', () => {
  const now = '2026-10-02T12:00:00Z';
  assert.equal(submissionDeadline(null, now), null);
  assert.equal(submissionDeadline('invalid', now), null);
  assert.equal(submissionDeadline(now, 'invalid'), null);
  assert.equal(submissionDeadline(now, now), 'Entry deadline passed');
  assert.equal(submissionDeadline('2026-10-01T12:00:00Z', now), 'Entry deadline passed');
  assert.equal(submissionDeadline('2026-10-02T12:00:01Z', now), 'Closes in 1 minute');
  assert.equal(submissionDeadline('2026-10-02T13:00:00Z', now), 'Closes in 1 hour');
  assert.equal(submissionDeadline('2026-10-03T12:00:00Z', now), 'Closes in 1 day');
  assert.equal(submissionDeadline('2026-10-05T12:00:00Z', now), 'Closes in 3 days');
});

test('competition attention respects server availability and editor eligibility', () => {
  const ready = activeMember();
  assert.equal(dashboardAttention(ready).find(item => item.key === 'competition')?.urgent, true);
  for (const flag of ['enabled', 'configuration_ready', 'can_submit']) {
    const data = structuredClone(ready);
    data.league[flag] = false;
    assert.equal(dashboardAttention(data).some(item => item.key === 'competition'), false, flag);
  }
  const visitor = structuredClone(ready);
  visitor.member.verified_editor = false;
  assert.equal(dashboardAttention(visitor).some(item => item.key === 'competition'), false);
  ready.league.next_entry = { id: 80, title: 'Next edit', state: 'eligible', video_url: 'https://video.example.test/80', detail_url: '/editing-hub#entry-80' };
  assert.equal(dashboardAttention(ready).find(item => item.key === 'competition')?.urgent, false);
  assert.match(dashboardAttention(ready).find(item => item.key === 'competition')?.detail, /Submitted/);
});

test('order attention identifies the order that actually needs action and its payment state', () => {
  for (const [status, label] of [['open', 'Awaiting payment'], ['processing', 'Payment processing'], ['failed', 'Payment failed'], ['review_required', 'Our team is reviewing this payment']]) {
    const data = emptyMember();
    data.orders = [order('1048'), order('1047', status)];
    const item = dashboardAttention(data).find(item => item.key === 'order');
    assert.ok(item, status);
    assert.equal(item.href, '/account/orders/1047');
    assert.match(`${item.label} ${item.detail}`, /1047/);
    assert.equal(item.detail, label);
  }
  const data = emptyMember();
  data.orders = [order('1048')];
  assert.equal(dashboardAttention(data).some(item => item.key === 'order'), false);
});

test('attention remains compact and omits stale event decisions or inactive account areas', () => {
  assert.deepEqual(dashboardAttention(emptyMember()), []);
  assert.ok(dashboardAttention(activeMember()).length <= 4);
  const data = emptyMember();
  data.applications.events = [{ id: 8, event_id: 4, title: 'Past event', status: 'accepted', applied_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-02T00:00:00Z', url: '/applications/8' }];
  assert.deepEqual(dashboardAttention(data), []);
  data.applications.events[0].status = 'pending';
  assert.equal(dashboardAttention(data)[0]?.key, 'event');
  data.applications.events[0].status = 'accepted';
  data.applications.events[0].updated_at = '2026-10-01T00:00:00Z';
  assert.equal(dashboardAttention(data)[0]?.detail, 'Event application · approved');
});

test('new members see useful empty states without invented rankings, results or orders', () => {
  const data = emptyMember();
  // Extra stale fields must not leak a follower-based standing into the V2 UI.
  data.member.follower_rank = 1;
  data.member.followers = 999999;
  const $ = renderDashboard(data);
  assert.equal($('h1').text(), 'Sample Editor');
  assert.match($('.v2-member-caught-up').text(), /caught up/);
  assert.equal($('.v2-member-rank').text(), 'Unranked');
  assert.equal($('.v2-member-points').text(), '—');
  assert.match($('.v2-member-competition').text(), /No official ranking yet/);
  assert.match($('.v2-member-competition').text(), /Results will appear after scoring/);
  assert.match($('.v2-member-first-edit').text(), /Your first edit starts here/);
  assert.equal($('.v2-member-first-edit a').attr('href'), '/editing-hub/apply');
  assert.equal($('.v2-member-latest-result').length, 0);
  assert.equal($('.v2-member-season').length, 0);
  assert.equal($('.v2-member-orders').length, 0);
  assert.doesNotMatch($('body').text(), /999999|followers|follower rank/i);
});

test('official league values and genuine zero points remain distinct from missing results', () => {
  const data = activeMember();
  data.league.month.points = 0;
  const $ = renderDashboard(data);
  assert.equal($('.v2-member-rank').text(), '#18');
  assert.equal($('.v2-member-points').text(), '0');
  assert.match($('.v2-member-latest-result').text(), /#7 · 185 points/);
  assert.match($('.v2-member-competition').text(), /2 places gained/);
  assert.match($('.v2-member-season').text(), /0 points/);
  assert.match($('.v2-member-season').text(), /October · #18/);
});

test('section order keeps member identity, attention and competition ahead of secondary activity', () => {
  const $ = renderDashboard(activeMember());
  const relevantSections = $('.v2-member-identity, section[aria-labelledby]').map((_, element) => $(element).attr('aria-labelledby') || 'member-identity').get();
  assert.deepEqual(relevantSections, ['member-identity', 'member-attention-title', 'member-league-title', 'member-latest-edit-title', 'member-applications-title', 'member-notifications-title', 'member-orders-title', 'member-quick-title']);
});

test('latest edit uses the real media and detail destination while keeping unscored results neutral', () => {
  const data = activeMember();
  const $ = renderDashboard(data);
  const panel = $('.v2-member-edit');
  assert.equal(panel.find('.v2-member-edit-preview img').attr('src'), data.latest_edit.thumbnail);
  assert.equal(panel.find('.v2-member-edit-preview').attr('href'), data.latest_edit.detail_url);
  assert.equal(panel.find('h3').first().text(), data.latest_edit.title);
  assert.match(panel.text(), /Your official result will appear after scoring/);
  assert.equal(panel.find('.v2-member-edit-results').length, 0);
  assert.equal(panel.find('a[href="/account/edits"]').length, 1);
});

test('missing thumbnail keeps a usable creative preview and invalidated submissions avoid scoring promises', () => {
  const data = activeMember();
  data.latest_edit.thumbnail = null;
  data.latest_edit.state = 'disqualified';
  const $ = renderDashboard(data);
  assert.equal($('.v2-member-edit-preview img').length, 0);
  assert.match($('.v2-member-edit-placeholder').text(), /Optimus Prime \| Rise Again/);
  assert.match($('.v2-member-edit-placeholder').text(), /Preview unavailable/);
  assert.match($('.v2-member-edit-body').text(), /This submission has no official result/);
  assert.doesNotMatch($('.v2-member-edit-body').text(), /result will appear after scoring/);
});

test('applications combine editor channels and recent events with actionable destinations', () => {
  const $ = renderDashboard(activeMember());
  const panel = $('.v2-member-applications');
  assert.match(panel.text(), /YouTube Editor/);
  assert.match(panel.text(), /TikTok Editor/);
  assert.match(panel.text(), /Approved/);
  assert.match(panel.text(), /Confirm channel/);
  assert.match(panel.text(), /Community showcase/);
  assert.equal(panel.find('a[href="/applications"]').length, 1);
  assert.equal(panel.find('a[href="/applications/8"]').length, 1);
});

test('unconfirmed editor applications invite confirmation before claiming admin review', () => {
  const data = activeMember();
  const application = data.applications.editors.find(item => item.status === 'pending');
  application.url = '/applications/editors/42';
  application.channel_verified = false;
  let attention = dashboardAttention(data).find(item => item.key === `editor-${application.platform}`);
  assert.equal(attention.detail, 'Confirm your channel to submit');
  assert.equal(attention.href, '/applications/editors/42');
  application.channel_verified = true;
  attention = dashboardAttention(data).find(item => item.key === `editor-${application.platform}`);
  assert.equal(attention.detail, 'Application under review');
  assert.match(renderDashboard(data)('.v2-member-editor-apps').text(), /Under review/);
});

test('notification preview is bounded, marks unread activity and preserves the full center link', () => {
  const $ = renderDashboard(activeMember());
  assert.equal($('.v2-member-notification-list li').length, 4);
  assert.equal($('.v2-member-notification-list a.unread').length, 3);
  assert.equal($('.v2-member-notifications a[href="/notifications"]').length, 1);
  assert.doesNotMatch($('.v2-member-notifications').text(), /Update 5/);
  const earlierOnly = emptyMember();
  earlierOnly.notifications.unread_count = 3;
  const earlierPreview = renderDashboard(earlierOnly)('.v2-member-notifications');
  assert.match(earlierPreview.text(), /Your inbox has earlier updates/);
  assert.doesNotMatch(earlierPreview.text(), /You’re up to date/);
});

test('orders preserve payment versus fulfillment state and link to the matching detail page', () => {
  const data = activeMember();
  data.orders[0].fulfillment_status = 'fulfilled';
  data.orders[0].fulfillment_note = 'Your order is ready.';
  const $ = renderDashboard(data);
  const cards = $('.v2-member-order');
  assert.equal(cards.length, 2);
  assert.match(cards.eq(0).text(), /Fulfilled/);
  assert.match(cards.eq(0).text(), /Your order is ready/);
  assert.equal(cards.eq(0).find('a').attr('href'), '/account/orders/1048');
  assert.equal(cards.eq(1).find('a').attr('href'), '/account/orders/1047');
  assert.doesNotMatch(cards.eq(1).text(), /Fulfilled/);
});

test('secondary account functions stay accessible without displaying settings forms in the overview', () => {
  const $ = renderDashboard(emptyMember(), { onRefresh: () => {} });
  for (const href of ['/favorites', '/account/orders', '/applications', '/notifications', '/account/profile', '/account/settings', '/account/preferences']) {
    assert.equal($(`nav[aria-label="Account shortcuts"] a[href="${href}"]`).length, 1, href);
  }
  assert.equal($('a[href="/account/profile"]').length, 2);
  assert.equal($('form, input[type="password"], input[type="email"]').length, 0);
  assert.equal($('button[aria-label="Refresh member dashboard"]').length, 1);
});

