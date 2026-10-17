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

// Render the real TSX in memory, using the frontend's installed dependencies.
// Application code is real; CSS module class names use stable keys because
// Node does not run Next's CSS loader. No generated build files are written.
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
    const base = specifier.startsWith('@/') ? resolve(frontendRoot, specifier.slice(2)) : resolve(dirname(filename), specifier);
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
const { filterStandings, standingsPath, standingsStatus } = loadComponent(resolve(frontendRoot, 'lib/league-presentation.ts'));
const { Standings, WinnerCard, LeagueRules, ChannelEligibilityNotice, ScoreBreakdown } = loadComponent(resolve(frontendRoot, 'components/platform/league.tsx'));

test('debut explains the actual weighted bonus and views while archived scores retain likes', () => {
  const score = { scoring_method: 'round_cohort_v2', popularity_metric: 'views', improvement_score: '85', improvement_weight: '.3', debut_bonus: true, likes: '250', views: '10000' };
  const $ = load(renderToStaticMarkup(createElement(ScoreBreakdown, { score })));
  assert.match($.text(), /Total views/);
  assert.match($.text(), /Debut · first competition week only/);
  assert.match($.text(), /25.5 to your overall edit score/);
  assert.match($.text(), /adds no extra league points/);
  assert.doesNotMatch($.text(), /neutral at 50|fewer than five/);
  const legacy = load(renderToStaticMarkup(createElement(ScoreBreakdown, { score: { popularity_metric: 'likes', neutral_baseline: true } })));
  assert.match(legacy.text(), /Total likes/);
  assert.doesNotMatch(legacy.text(), /Total views|Debut/);
});

test('returning editors see their saved history rather than an invented debut', () => {
  const score = { scoring_method: 'round_cohort_v2', baseline_sample_count: 2, baseline_median_likes: '150', likes: '300', views: '10000', relative_performance: '2' };
  const $ = load(renderToStaticMarkup(createElement(ScoreBreakdown, { score })));
  assert.match($.text(), /2 previous finalized website edits · median 150 likes/);
  assert.match($.text(), /2.00×/);
  assert.doesNotMatch($.text(), /Debut|fewer than five/);
});

test('revised public rules disclose 85 debut, last-five history, views and unvalidated status', () => {
  const $ = load(renderToStaticMarkup(createElement(LeagueRules, {
    status: { scoring_method: 'round_cohort_v2', debut_improvement_score: '85', weights: { response: '.5', improvement: '.3', popularity: '.2' } },
  })));
  assert.match($.text(), /Total views/);
  assert.match($.text(), /85\/100/);
  assert.match($.text(), /one to five distinct finalized website edits/);
  assert.match($.text(), /not a validated fairness model/);
  assert.doesNotMatch($.text(), /popularity compares lifetime likes|fewer than five trustworthy/);
});

test('monthly award identifies the editor and labels the video as representative', () => {
  const html = renderToStaticMarkup(createElement(WinnerCard, {
    title: 'Editor of the Month', monthly: true, state: 'finalized', loading: false, error: null, retry() {},
    winner: { username: 'Editor', period_label: '2026-07', points: 72, weekly_score: '89.5', title: 'Example edit', video_url: 'https://example.test/edit' },
  }));
  const $ = load(html);
  assert.match($('h2').text(), /Editor of the Month/);
  assert.match($.text(), /Representative edit/);
  assert.match($.text(), /72monthly league points/);
  assert.doesNotMatch($.text(), /Edit of the Month|annual/i);
});

test('monthly rules explain reset, open joining and unvalidated scoring honestly', () => {
  const $ = load(renderToStaticMarkup(createElement(LeagueRules, {
    status: { configuration_ready: false, weights: { response: '.5', improvement: '.3', popularity: '.2' } },
  })));
  assert.match($.text(), /zero monthly points/);
  assert.match($.text(), /no catch-up bonus/);
  assert.match($.text(), /proposed weights/);
  assert.match($.text(), /reuploads cannot always be detected/);
  assert.doesNotMatch($.text(), /annual/i);
});

function standings(period = 'month') {
  return {
    period, period_label: period === 'week' ? '28 Sep – 02 Oct 2026' : '2026-10',
    state: period === 'week' ? 'finalized' : 'accumulating', provisional: period !== 'week', result_revision: 2,
    rows: [
      { editor_id: 1, username: 'Alpha', channel_name: 'Prime cuts', platform: 'youtube', channel_verified: true, rank: 1, points: 200, weekly_score: 92.25, scored_rounds: 3, latest_result: { rank: 1, points: 50, period_label: 'Closing round' }, rank_change: null },
      { editor_id: 2, username: 'Beta', channel_name: 'Rising edits', platform: 'tiktok', rank: 7, points: 150, weekly_score: 76.5, scored_rounds: 2, latest_result: { rank: 7, points: 35, period_label: 'Closing round' }, rank_change: null },
      { editor_id: 3, username: 'Gamma', channel_name: 'Rising robots', platform: 'tiktok', rank: 7, points: 150, weekly_score: 76.5, scored_rounds: 2, latest_result: { rank: 7, points: 35, period_label: 'Closing round' }, rank_change: null },
    ],
  };
}

function render(data, props = {}) {
  return load(renderToStaticMarkup(createElement(Standings, { data, search: '', platform: '', onSearch() {}, onPlatform() {}, ...props })));
}
function positions($) { return $('tbody td.v2-league-position-cell').map((_, cell) => $(cell).text()).get(); }
function headers($) { return $('thead th').map((_, cell) => $(cell).text()).get(); }

test('search and platform filters preserve published order, placements, and ties', () => {
  const data = standings();
  const original = structuredClone(data.rows);
  assert.deepEqual(filterStandings(data.rows, ' RISING ', 'tiktok').map(row => row.rank), [7, 7]);
  assert.deepEqual(data.rows, original);
  const $ = render(data, { search: 'rising', platform: 'tiktok', currentUserId: 2 });
  assert.deepEqual(positions($), ['7', '7']);
  assert.equal($('.v2-league-match-count').text(), '2 of 3 editors');
  assert.equal($('tbody tr.is-current-user').length, 1);
  assert.match($('tr.is-current-user').text(), /BetaYou/);
  assert.equal($('tbody tr.is-leader').length, 0);
});

test('official league points and weekly scores have distinct table columns', () => {
  const monthly = render(standings());
  assert.deepEqual(headers(monthly), ['Pos', 'Editor / channel', 'Latest result', 'League points']);
  assert.equal(monthly('tbody .v2-league-points-cell strong').first().text(), '200');
  assert.equal(monthly('tbody .v2-league-score-cell').length, 0);
  assert.equal(monthly('.v2-league-match-count').text(), 'Official position order');
  const weekly = render(standings('week'));
  assert.deepEqual(headers(weekly), ['Pos', 'Editor / channel', 'Edit score / 100', 'League points', 'Score breakdown']);
  assert.equal(weekly('tbody .v2-league-score-cell strong').first().text(), '92.25');
  assert.equal(weekly('tbody .v2-league-points-cell strong').first().text(), '200');
  assert.equal(weekly('.v2-league-result-status').text(), 'Official result');
  assert.equal(weekly('button[aria-label="Show score breakdown for Alpha"]').attr('aria-expanded'), 'false');
  assert.match(weekly('.v2-league-results-footnote').text(), /Revision 2/);
});

test('live placement stays provisional and missing data never becomes a zero score or rank', () => {
  const data = standings('week');
  data.state = 'live'; data.provisional = true;
  data.rows[0].points = null;
  data.rows[1] = { ...data.rows[1], rank: null, points: null, weekly_score: null, state: 'data_pending' };
  data.rows[2] = { ...data.rows[2], rank: null, points: null, weekly_score: 0 };
  const $ = render(data);
  assert.equal($('.v2-league-result-status').text(), 'Provisional standings');
  assert.equal($('.v2-league-match-count').text(), 'Provisional position order');
  assert.deepEqual(positions($), ['1', '—', '—']);
  assert.equal($('tbody .v2-league-score-cell strong').eq(1).text(), '—');
  assert.equal($('tbody .v2-league-score-cell strong').eq(2).text(), '0.00');
  assert.equal($('tbody .v2-league-points-cell strong').first().text(), '—');
  assert.match($('tbody tr').eq(1).text(), /Data pending/);
  assert.doesNotMatch($('caption').text(), /official positions/i);
});

test('aggregate latest results remain available in compact mobile identities', () => {
  for (const period of ['month']) {
    const data = standings(period);
    data.rows[1].latest_result.points = 0;
    data.rows[2].latest_result = null;
    const $ = render(data);
    assert.equal($('.v2-league-mobile-latest').length, 2);
    assert.equal($('.v2-league-mobile-latest').first().text(), 'Latest: #1 · 50 pts');
    assert.equal($('.v2-league-mobile-latest').first().attr('title'), 'Closing round');
    assert.equal($('.v2-league-mobile-latest').eq(1).text(), 'Latest: #7 · 0 pts');
    assert.equal($('tbody tr').eq(2).find('.v2-league-mobile-latest').length, 0);
  }
  assert.equal(render(standings('week'))('.v2-league-mobile-latest').length, 0);
});

test('movement and latest-result columns require actual available data', () => {
  const data = standings();
  data.rows.forEach(row => { row.latest_result = null; });
  assert.deepEqual(headers(render(data)), ['Pos', 'Editor / channel', 'League points']);
  data.rows[0].rank_change = 2;
  data.rows[1].rank_change = -1;
  const $ = render(data);
  assert.ok(headers($).includes('Change'));
  assert.equal($('[aria-label="Up 2 places"]').length, 1);
  assert.equal($('[aria-label="Down 1 places"]').length, 1);
  assert.equal($('[aria-label="Rank change unavailable"]').length, 1);
});

test('new competition empty states do not invent follower-based results', () => {
  const data = { ...standings('week'), state: 'scheduled', provisional: true, rows: [], follower_rank: 1, followers: 999999 };
  const $ = render(data);
  assert.match($('.v2-league-empty-results').text(), /No official ranking yet/);
  assert.match($('.v2-league-empty-results').text(), /Results will appear after scoring/);
  assert.equal($('.v2-league-empty-results a').attr('href'), '#league-entry');
  assert.equal($('.v2-league-table-tools').length, 0);
  assert.equal($('.v2-league-empty-cell').attr('colspan'), String($('thead th').length));
  assert.doesNotMatch($('body').text(), /999999|follower/i);
});

test('unpublishable finalized results avoid claims that official scores exist or are frozen', () => {
  for (const state of ['finalized', 'corrected']) {
    const $ = render({ ...standings('week'), state, rows: [] });
    assert.equal($('.v2-league-result-status').text(), 'No official results available');
    assert.match($('.v2-league-empty-results').text(), /No official results are currently available/);
    assert.doesNotMatch($('body').text(), /These results are frozen|Results will appear after scoring/);
  }
});

test('exhibition and canceled rounds explain why they have no official points', () => {
  for (const [state, title, status] of [
    ['exhibition', 'Exhibition round', 'Exhibition · no league points'],
    ['canceled', 'This round was canceled', 'Round canceled'],
  ]) {
    const $ = render({ ...standings('week'), state, rows: [] });
    assert.equal($('.v2-league-result-status').text(), status);
    assert.equal($('.v2-league-empty-results h4').text(), title);
    assert.doesNotMatch($('.v2-league-empty-results').text(), /Results will appear after scoring/);
  }
});

test('no search matches retain contextual columns and offer a clear reset', () => {
  const data = standings(); data.rows[0].rank_change = 0;
  const $ = render(data, { search: 'No matching name' });
  assert.equal($('.v2-league-empty-results h4').text(), 'No matching editors');
  assert.equal($('.v2-league-empty-results button').text(), 'Clear filters');
  assert.equal($('.v2-league-match-count').text(), '0 of 3 editors');
  assert.equal($('.v2-league-empty-cell').attr('colspan'), String($('thead th').length));
  assert.doesNotMatch($('.v2-league-empty-results').text(), /No official ranking yet/);
});

test('round queries keep archived context distinct from current round defaults', () => {
  assert.equal(standingsPath('month', '2025', '3', '9'), 'league/standings/?period=month&year=2025&month=3');
  assert.equal(standingsPath('month', '2025', '3', '9'), 'league/standings/?period=month&year=2025&month=3');
  assert.equal(standingsPath('week', '2025', '3', '9'), 'league/standings/?period=week&week=9');
  assert.equal(standingsPath('week', '', '', ''), 'league/standings/?period=week');
  const encoded = new URLSearchParams(standingsPath('week', '', '', '9&year=2020').split('?')[1]);
  assert.equal(encoded.get('week'), '9&year=2020');
  assert.equal(encoded.has('year'), false);
  assert.equal(standingsStatus({ period: 'month', state: 'accumulating', provisional: true }), 'Finalized round points');
  assert.equal(standingsStatus({ period: 'week', state: 'finalizing', provisional: true }), 'Results pending');
});


test('monthly standings distinguish accumulating, finalizing and frozen results', () => {
  assert.equal(standingsStatus({ period: 'month', state: 'accumulating', provisional: true }), 'Finalized round points');
  assert.equal(standingsStatus({ period: 'month', state: 'finalizing', provisional: true }), 'Month results pending');
  assert.equal(standingsStatus({ period: 'month', state: 'finalized', provisional: false }), 'Finalized monthly standings');
});


test('automatic rules disclose the actual starter method and configured point awards', () => {
  const $ = load(renderToStaticMarkup(createElement(LeagueRules, { status: {
    configuration_ready: true, scoring_method: 'round_cohort_v1', scoring_validated: false,
    weights: { response: '.5', improvement: '.3', popularity: '.2' },
    placement_points: [30,20,16,13,11,10,9,8,7,6], finisher_points: 3, minimum_entries: 5,
  } })));
  assert.match($.text(), /Automatic starter scoring/);
  assert.match($.text(), /not a validated fairness model/);
  assert.match($.text(), /30, 20, 16/);
  assert.match($.text(), /other eligible finishers earn 3/);
  assert.match($.text(), /5 eligible entries/);
  assert.doesNotMatch($.text(), /real provider calibration is still required/);
});


test('approved unconfirmed channels link to their existing confirmation instead of an application loop', () => {
  const $ = load(renderToStaticMarkup(createElement(ChannelEligibilityNotice, { applications: [
    { id: 3, platform: 'youtube', channel_name: 'Approved creator', status: 'accepted', channel_verified: false, removal_requested: false },
  ] })));
  assert.match($.text(), /Approved.*confirm/);
  assert.match($.text(), /do not need to apply again/);
  assert.equal($('a').attr('href'), '/applications/editors/3');
  assert.equal($('a[href="/editing-hub/apply"]').length, 0);
});

test('pending, removed and new channels get distinct eligibility instructions', () => {
  for (const [application, expected] of [
    [{ status: 'pending', channel_verified: true }, /under review/],
    [{ status: 'accepted', channel_verified: true, removal_requested: true }, /Removal requested/],
    [{ status: 'rejected' }, /not approved/],
  ]) {
    const $ = load(renderToStaticMarkup(createElement(ChannelEligibilityNotice, { applications: [{ id: 4, channel_name: 'Creator', ...application }] })));
    assert.match($.text(), expected);
    assert.equal($('a').attr('href'), '/applications/editors/4');
  }
  const $ = load(renderToStaticMarkup(createElement(ChannelEligibilityNotice, {})));
  assert.equal($('a').attr('href'), '/editing-hub/apply');
});


test('live points are backend projections, distinct from final awards and missing data', () => {
  const data = standings('week');
  data.state = 'live'; data.provisional = true; data.minimum_entries = 5;
  data.rows[0] = { ...data.rows[0], points: null, projected_points: 31, video_url: 'https://youtu.be/AbCdEfGhI_1' };
  data.rows[1] = { ...data.rows[1], points: null, projected_points: 20 };
  data.rows[2] = { ...data.rows[2], points: null, projected_points: null, rank: null, weekly_score: null };
  const $ = render(data);
  assert.deepEqual($('tbody .v2-league-points-cell strong').map((_, node) => $(node).text()).get(), ['31', '20', '—']);
  assert.equal($('tbody .v2-league-points-cell span').first().text(), 'Projected');
  assert.match($.text(), /3 of 5 required entries/);
  assert.equal($('a.v2-league-watch-link').attr('href'), 'https://youtu.be/AbCdEfGhI_1');
  assert.equal($('[role="img"][aria-label="YouTube"]').length, 1);
  assert.equal($('[role="img"][aria-label="TikTok"]').length, 2);
  data.state = 'finalized'; data.provisional = false; data.rows[0].points = 25;
  assert.equal(render(data)('tbody .v2-league-points-cell strong').first().text(), '25');
});

test('all-time navigation excludes calendar filters and explains non-duplicated awards', () => {
  assert.equal(standingsPath('all_time', 2026, 10, 5), 'league/standings/?period=all_time');
  const $ = render(standings('all_time'));
  assert.match($.text(), /Monthly totals are not counted twice/);
});

test('winner media supports only recognized provider URLs with no eager iframe', () => {
  const { leagueMedia } = loadComponent(resolve(frontendRoot, 'lib/league-media.ts'));
  assert.match(leagueMedia('https://youtu.be/M7lc1UVf-VE').embed, /^https:\/\/www.youtube-nocookie.com\/embed\/M7lc1UVf-VE/);
  assert.match(leagueMedia('https://www.tiktok.com/@demo/video/6718335390845095173').embed, /player\/v1\/6718335390845095173/);
  for (const value of ['javascript:alert(1)', 'https://youtube.com.evil.test/watch?v=M7lc1UVf-VE', 'https://user@youtube.com/watch?v=M7lc1UVf-VE', 'https://youtube.com/watch?v=bad']) assert.equal(leagueMedia(value), null);
  const { WinnerMedia } = loadComponent(resolve(frontendRoot, 'components/platform/league-media.tsx'));
  const $ = load(renderToStaticMarkup(createElement(WinnerMedia, { videoUrl: 'https://youtu.be/M7lc1UVf-VE', title: 'Winner' })));
  assert.equal($('iframe').length, 0);
  assert.equal($('button[aria-label="Play Winner"]').length, 1);
  assert.match($('img').attr('src'), /i.ytimg.com/);
});
