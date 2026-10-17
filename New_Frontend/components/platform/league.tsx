'use client';

import { Fragment, useCallback, useEffect, useId, useState, type FormEvent } from 'react';
import { ArrowDown, ArrowUp, ArrowUpRight, ChevronDown, Flag, RotateCw, Search, ShieldCheck, Trophy } from 'lucide-react';
import { api, mutate, safeUrl } from '@/lib/api';
import { browsableRounds, filterStandings, platformLabel, standingsPath, standingsStatus, type HubStanding, type HubStandings, type LeagueRounds } from '@/lib/league-presentation';
import type { MemberDashboard } from '@/lib/member-dashboard';
import {
  canEnterLeague, cutoffCountdown, leagueNumber, leagueStateLabel, leagueStateMessage,
  pointsLabel, scoreLabel, type LeagueEntry, type LeaguePeriod, type LeagueScore,
  type LeagueStatus, type LeagueWeek, type LeagueWinner,
  type LeagueWinners, type OwnLeagueEntries, type VerifiedLeagueChannel,
} from '@/lib/league-view';
import { useSite } from './site-shell';
import { Empty, ErrorNotice, Field, Loading, Notice } from './ui';
import { PlatformIcon, WinnerMedia } from './league-media';
import { EditorTitle } from './editor-title';

// Keep a successful response visible while refreshing. In particular, a background
// status refresh must not unmount a partially completed submission form.
function useLeagueResource<T>(path: string | null) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ path: string | null; data: T | null; error: Error | null; loading: boolean }>({ path, data: null, error: null, loading: Boolean(path) });
  const reload = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    if (!path) { setState({ path, data: null, error: null, loading: false }); return; }
    const controller = new AbortController();
    setState(previous => ({ path, data: previous.path === path ? previous.data : null, error: null, loading: true }));
    api<T>(path, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) })
      .then(data => { if (!controller.signal.aborted) setState({ path, data, error: null, loading: false }); })
      .catch(error => { if (!controller.signal.aborted) setState(previous => ({ ...previous, error: error as Error, loading: false })); });
    return () => controller.abort();
  }, [path, revision]);
  return { data: state.path === path ? state.data : null, error: state.path === path ? state.error : null, loading: state.path !== path || state.loading, reload };
}

function LocalTime({ value, fallback = 'Not scheduled' }: { value?: string | null; fallback?: string }) {
  const [localized, setLocalized] = useState(false);
  useEffect(() => setLocalized(true), []);
  if (!value || !Number.isFinite(Date.parse(value))) return <span>{fallback}</span>;
  const date = new Date(value);
  return <time dateTime={value} title={date.toUTCString()}>{new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short', ...(localized ? {} : { timeZone: 'UTC' }) }).format(date)}</time>;
}
function Countdown({ week }: { week: LeagueWeek }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, []);
  const countdown = now === null ? null : cutoffCountdown(week.cutoff_at, now);
  return countdown ? <span className="v2-league-countdown">{countdown}</span> : null;
}

export function EditingHubPage() {
  const { user } = useSite();
  const [period, setPeriod] = useState<LeaguePeriod>('week');
  const [year, setYear] = useState('');
  const [month, setMonth] = useState('');
  const [week, setWeek] = useState('');
  const [search, setSearch] = useState('');
  const [platform, setPlatform] = useState('');
  const status = useLeagueResource<LeagueStatus>('league/status/');
  const winners = useLeagueResource<LeagueWinners>('league/winners/');
  const rounds = useLeagueResource<LeagueRounds>(`league/rounds/${year ? `?year=${year}` : ''}`);
  const member = useLeagueResource<MemberDashboard>(user ? 'member/dashboard/' : null);
  // An archived year must never display this week's result under its label.
  const archiveRounds = browsableRounds(rounds.data);
  const selectedWeek = week || (year ? String(archiveRounds[0]?.id || '') : '');
  const selectedMonth = month || (year ? String(rounds.data?.months?.[0]?.month || '') : '');
  const awaitingRound = period === 'week' && Boolean(year) && !selectedWeek;
  const awaitingMonth = period === 'month' && Boolean(year) && !selectedMonth;
  const standings = useLeagueResource<HubStandings>(awaitingRound || awaitingMonth ? null : standingsPath(period, year, selectedMonth, selectedWeek));
  const refresh = useCallback(() => { status.reload(); winners.reload(); standings.reload(); rounds.reload(); member.reload(); }, [status.reload, winners.reload, standings.reload, rounds.reload, member.reload]);
  useEffect(() => {
    const timer = window.setInterval(() => { if (!document.hidden) refresh(); }, 60000);
    const onVisibility = () => { if (!document.hidden) refresh(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisibility); };
  }, [refresh]);
  const refreshing = status.loading || winners.loading || standings.loading || rounds.loading;
  const competitionState = !status.data?.enabled ? 'Preparing the league' : !status.data.configuration_ready ? 'Scoring setup pending' : leagueStateLabel(status.data.current_week?.state);
  const choosePeriod = (value: LeaguePeriod) => { setPeriod(value); setSearch(''); setPlatform(''); };
  return <div className="v2-container v2-page v2-league-page">
    <header className="v2-league-masthead">
      <div><span className="v2-eyebrow"><Flag size={14} aria-hidden="true" /> Community competition</span><h1>Editing league<span>.</span></h1><p>The edits. The results. The race to the top.<br />Your official home for league standings.</p></div>
      <div className="v2-league-masthead-side"><span className="v2-league-season-mark">{status.data?.month?.name || 'Editing Hub'}</span><span className="v2-league-live-label"><i aria-hidden="true" />{status.loading && !status.data ? 'Checking competition status' : status.error && !status.data ? 'Status unavailable' : competitionState}</span><a href="#league-entry" className="v2-button compact v2-league-header-action">{user ? 'Manage your entry' : 'Join the competition'}<ArrowUpRight size={17} aria-hidden="true" /></a></div>
    </header>
    <nav className="v2-league-section-nav" aria-label="Editing league sections"><a href="#league-standings">Standings</a><a href="#league-highlights">Highlights</a><a href="#league-entry">Your entry</a><a href="#league-rules-title">How scoring works</a><a href="/editing-hub/apply">Become an editor</a>{user?.is_staff && <a href="/admin/edithub/leaguesettings/">League settings</a>}</nav>

    <section className="v2-panel v2-section-heading"><div><span className="v2-eyebrow">Your editor profile</span><h2>{member.data?.member.verified_editor ? 'Your channel is approved' : 'Start with your channel'}</h2><p className="v2-muted">{member.data?.member.verified_editor ? 'Manage your editor applications and explore upcoming rounds.' : 'Editor applications are open. Connect your YouTube or TikTok channel before your first competition.'}</p></div><a className="v2-button secondary compact" href={member.data?.member.verified_editor ? '/applications' : '/editing-hub/apply'}>{member.data?.member.verified_editor ? 'Your applications' : 'Become an editor'}<ArrowUpRight size={17} aria-hidden="true" /></a></section>

    {user && <MemberLeagueSummary data={member.data} loading={member.loading} error={member.error} retry={member.reload} />}

    <section id="league-standings" className="v2-league-standings-section" aria-labelledby="league-standings-title">
      <span id="league-rounds" className="v2-league-anchor" aria-hidden="true" />
      <ErrorNotice error={status.error} retry={status.reload} />
      {status.data && <LeagueClock status={status.data} stale={Boolean(status.error)} />}
      <div className="v2-section-heading"><div><span className="v2-eyebrow">Every result counts</span><h2 id="league-standings-title">League standings</h2></div><button className="v2-league-refresh-button" type="button" onClick={refresh} disabled={refreshing} aria-label={refreshing ? 'Refreshing league data' : 'Refresh league data'}><RotateCw size={16} aria-hidden="true" /><span>{refreshing ? 'Refreshing' : 'Refresh'}</span></button></div>
      <div className="v2-league-context">
        <div className="v2-league-periods" role="group" aria-label="Standings period">{(['week', 'month', 'all_time'] as const).map(value => <button key={value} type="button" className={period === value ? 'active' : ''} aria-pressed={period === value} onClick={() => choosePeriod(value)}>{value === 'week' ? 'Weekly league' : value === 'all_time' ? 'All-time points' : 'Monthly league'}</button>)}</div>
        <div className="v2-league-context-selects">{period !== 'all_time' && <label><span>Calendar year</span><select value={year} onChange={event => { setYear(event.target.value); setWeek(''); setMonth(''); setSearch(''); setPlatform(''); }}><option value="">Current year</option>{rounds.data?.years.map(season => <option key={season.id} value={season.year}>{season.name}</option>)}</select></label>}
          {period === 'month' && <label><span>Month</span><select value={selectedMonth} onChange={event => setMonth(event.target.value)} disabled={Boolean(year) && !rounds.data?.months?.length}>{!year && <option value="">Current month</option>}{year && !rounds.data?.months?.length && <option value="">No months available</option>}{rounds.data?.months?.map(item => <option key={item.month} value={item.month}>{item.label}</option>)}</select></label>}
          {period === 'week' && <label className="v2-league-round-select"><span>Week</span><select value={selectedWeek} onChange={event => setWeek(event.target.value)} disabled={Boolean(year) && !archiveRounds.length}>{!year && <option value="">Current week</option>}{year && !archiveRounds.length && <option value="">No past rounds</option>}{archiveRounds.map(round => <option key={round.id} value={round.id}>{round.label} · {leagueStateLabel(round.state)}</option>)}</select></label>}
        </div>
      </div>
      <ErrorNotice error={rounds.error} retry={rounds.reload} />
      <ErrorNotice error={standings.error} retry={standings.reload} />
      {standings.error && standings.data && <p className="v2-small v2-muted">The latest refresh failed. The last successfully loaded standings are shown below.</p>}
      {standings.loading && !standings.data && <Loading label="Loading standings…" />}
      {(awaitingRound || awaitingMonth) && <Empty title={rounds.loading ? 'Loading calendar rounds…' : 'No rounds in this year yet'}>Choose another year or check the monthly standings.</Empty>}
      {standings.data && <Standings data={standings.data} currentUserId={user?.id} search={search} platform={platform} onSearch={setSearch} onPlatform={setPlatform} />}
      <p className="v2-small v2-muted v2-league-refresh">Metrics updated <LocalTime value={standings.data?.last_refresh || (period === 'week' && !selectedWeek ? status.data?.last_refresh : null)} fallback="when available" /> · Standings refresh automatically.</p>
    </section>
    <section id="league-highlights" className="v2-section v2-league-highlights-section" aria-labelledby="league-highlights-title"><div className="v2-section-heading"><div><span className="v2-eyebrow">The work that sets the pace</span><h2 id="league-highlights-title">League highlights</h2></div><Trophy size={25} aria-hidden="true" /></div><div className="v2-two-columns v2-league-showcases" aria-label="Finalized winner showcases"><WinnerCard title="Edit of the Week" winner={winners.data?.weekly_winner || null} state={winners.data?.weekly_state} monthly={false} loading={!winners.data && winners.loading} error={winners.error} retry={winners.reload} /><WinnerCard title="Editor of the Month" winner={winners.data?.monthly_winner || null} state={winners.data?.monthly_state} monthly loading={!winners.data && winners.loading} error={winners.error} retry={winners.reload} /></div></section>
    <section id="league-entry" className="v2-section v2-league-entry-section" aria-labelledby="league-entry-title"><div className="v2-section-heading"><div><span className="v2-eyebrow">Make your next move</span><h2 id="league-entry-title">Your league entry</h2></div></div><YourEntries status={status.data} onChange={refresh} /></section>
    <LeagueRules status={status.data} />
  </div>;
}

function MemberLeagueSummary({ data, loading, error, retry }: { data: MemberDashboard | null; loading: boolean; error: Error | null; retry: () => void }) {
  if (!data) return error ? <ErrorNotice error={error} retry={retry} /> : loading ? <Loading label="Loading your league position…" /> : null;
  const league = data.league;
  return <section className="v2-league-member-summary" aria-label="Your current league summary"><div className="v2-league-member-intro"><span className="v2-eyebrow">Your month</span><a href="/account">{data.member.display_name}<ArrowUpRight size={15} aria-hidden="true" /></a><EditorTitle name={data.member.editor_title} rarity={data.member.editor_title_rarity} /><span>{league.month.label || 'Current month'}</span></div><dl><div><dt>Official rank</dt><dd>{league.month.rank === null ? <span className="v2-league-summary-neutral">No official ranking yet</span> : `#${league.month.rank}`}</dd></div><div><dt>League points</dt><dd>{pointsLabel(league.month.points)}</dd></div><div><dt>Latest round</dt><dd>{league.latest_result?.rank ? `#${league.latest_result.rank}` : <span className="v2-league-summary-neutral">No completed result</span>}</dd>{league.latest_result && <span>{pointsLabel(league.latest_result.points)} points</span>}</div><div><dt>Next entry deadline</dt><dd className="v2-league-summary-date"><LocalTime value={league.submission_deadline} /></dd><span>{league.next_entry ? leagueStateLabel(league.next_entry.state) : league.can_submit ? 'Entries open' : 'Entries not open'}</span></div></dl>{error && <span className="v2-league-stale-note">Showing your last loaded summary.</span>}</section>;
}

export function LeagueClock({ status, stale }: { status: LeagueStatus; stale: boolean }) {
  const week = status.current_week;
  return <div className="v2-league-clock" aria-label="Live competition timer"><div><span className="v2-eyebrow">Current competition</span><strong>{week?.label || 'Next round coming soon'}</strong>{week && ['live', 'active'].includes(week.state) && <Countdown week={week} />}{week && !['live', 'active'].includes(week.state) && <span>{leagueStateLabel(week.state)}</span>}</div><div><span>Next entry deadline</span><strong><LocalTime value={status.next_week?.starts_at} /></strong><span>Entries join the following week · UTC competition schedule</span></div>{stale && <p className="v2-small v2-muted">Showing the last loaded schedule.</p>}</div>;
}

export function WinnerCard({ title, winner, monthly, state, loading, error, retry }: { title: string; winner: LeagueWinner | null; monthly: boolean; state?: string; loading: boolean; error: Error | null; retry: () => void }) {
  return <section className="v2-panel v2-league-winner"><span className="v2-eyebrow">{monthly ? 'Consistency across the month' : 'One edit. First place.'}</span><h2>{title}</h2>
    {error && <ErrorNotice error={error} retry={retry} />}
    {loading ? <Loading label="Loading finalized result…" /> : winner ? <>
      <span className="v2-league-winner-symbol" aria-hidden="true">✦</span><p className="v2-league-winner-period">{winner.period_label}</p><h3>{winner.username}</h3><EditorTitle name={winner.editor_title} rarity={winner.editor_title_rarity} /><p>{monthly && <span>Representative edit · </span>}{winner.title || 'Featured edit'}</p><WinnerMedia key={winner.video_url} videoUrl={winner.video_url} title={winner.title} format={winner.video_format} /><div className="v2-league-winner-numbers"><div><strong>{pointsLabel(winner.points)}</strong><span>{monthly ? 'monthly league points' : 'league points'}</span></div><div><strong>{scoreLabel(winner.weekly_score)}</strong><span>{monthly ? 'representative edit score' : 'edit score'}</span></div></div>
      {safeUrl(winner.video_url, '') && <><a className="v2-button secondary compact" href={safeUrl(winner.video_url)} target="_blank" rel="noopener noreferrer"><PlatformIcon platform={winner.platform} />View edit ↗</a><p className="v2-small v2-muted">If playback is unavailable here, open the original edit.</p></>}
      <p className="v2-small v2-muted">{monthly ? 'The monthly award reflects the editor’s accumulated league points. Representative edit: their strongest eligible edit from that month. The title adds no bonus points.' : 'The last finalized weekly winner is shown here while the next round runs.'}</p>
      {['finalizing', 'data_pending'].includes(state || '') && <p className="v2-small v2-muted">The latest period is still awaiting results. This card shows the last finalized winner.</p>}
    </> : !error && <Empty title={['finalizing', 'data_pending'].includes(state || '') ? 'Results pending' : 'No finalized winner yet'}>{state === 'exhibition' ? 'Exhibition rounds do not award an official winner.' : state === 'canceled' ? 'The round was canceled; no award was made.' : monthly ? 'A monthly winner appears after qualifying rounds and the month are finalized.' : 'The winner appears after a qualifying round is finalized.'}</Empty>}
  </section>;
}

export function Standings({ data, currentUserId, search, platform, onSearch, onPlatform }: { data: HubStandings; currentUserId?: number; search: string; platform: string; onSearch: (value: string) => void; onPlatform: (value: string) => void }) {
  const weekly = data.period === 'week';
  const [expanded, setExpanded] = useState<number | null>(null);
  const rowId = useId();
  const rows = filterStandings(data.rows, search, platform);
  const platforms = Array.from(new Set(data.rows.map(row => row.platform).filter((value): value is string => Boolean(value))));
  const hasLatest = !weekly && data.rows.some(row => row.latest_result);
  const hasMovement = data.rows.some(row => typeof row.rank_change === 'number');
  const columns = 3 + (weekly ? 2 : hasLatest ? 1 : 0) + (hasMovement ? 1 : 0);
  const unavailableFinal = weekly && ['finalized', 'corrected'].includes(data.state) && !data.rows.length;
  const positionOrder = weekly && data.provisional ? 'Provisional position order' : 'Official position order';
  const neutralTitle = data.state === 'exhibition' ? 'Exhibition round' : ['canceled', 'cancelled'].includes(data.state) ? 'This round was canceled' : 'No official ranking yet';
  const stateMessage = weekly && !unavailableFinal ? leagueStateMessage(data.state) : '';
  return <div className="v2-league-results">
    <div className="v2-league-result-heading"><div><h3>{data.period_label}</h3><span className={`v2-league-result-status${weekly && data.provisional ? ' provisional' : ''}`}>{standingsStatus(data)}</span></div><span className="v2-league-result-count">{data.rows.length} {data.rows.length === 1 ? 'editor' : 'editors'}</span></div>
    {data.rows.length > 0 && <div className="v2-league-table-tools"><label className="v2-league-editor-search"><Search size={17} aria-hidden="true" /><span className="v2-visually-hidden">Find an editor or channel</span><input type="search" value={search} placeholder="Find an editor or channel" onChange={event => onSearch(event.target.value)} /></label>{platforms.length > 1 && <label className="v2-league-platform-filter"><span className="v2-visually-hidden">Filter platform</span><select value={platform} onChange={event => onPlatform(event.target.value)}><option value="">All platforms</option>{platforms.map(value => <option key={value} value={value}>{platformLabel(value)}</option>)}</select></label>}<span className="v2-league-match-count" role="status">{search || platform ? `${rows.length} of ${data.rows.length} editors` : positionOrder}</span></div>}
    <div className="v2-league-table-container"><table className="v2-league-standings-table"><caption className="v2-visually-hidden">{data.period_label} — {standingsStatus(data)}. Filtering preserves published positions.</caption><thead><tr><th scope="col" className="v2-league-position-cell"><abbr title="Position">Pos</abbr></th><th scope="col">Editor / channel</th>{weekly && <th scope="col" className="v2-league-score-cell">Edit score <span>/ 100</span></th>}{hasLatest && <th scope="col" className="v2-league-latest-cell">Latest result</th>}<th scope="col" className="v2-league-points-cell">League points</th>{hasMovement && <th scope="col" className="v2-league-movement-cell">Change</th>}{weekly && <th scope="col" className="v2-league-details-cell"><span className="v2-visually-hidden">Score breakdown</span></th>}</tr></thead><tbody>
      {rows.map(row => <Fragment key={`${row.editor_id}-${row.entry_id || 'total'}`}><tr className={`${row.rank === 1 ? 'is-leader ' : ''}${row.editor_id === currentUserId ? 'is-current-user' : ''}`}><td className="v2-league-position-cell"><span>{row.rank ?? '—'}</span></td><th scope="row"><div className="v2-league-editor-identity"><EditorAvatar row={row} /><div><div className="v2-league-editor-name"><span>{row.username}</span>{weekly && row.debut_bonus && <span className="v2-league-you" title="First competition week: debut performance bonus">Debut</span>}{row.channel_verified && <ShieldCheck size={15} aria-label="Verified channel" />}{row.editor_id === currentUserId && <span className="v2-league-you">You</span>}</div><EditorTitle name={row.editor_title} rarity={row.editor_title_rarity} /><span className="v2-league-editor-channel">{row.channel_name || 'Editor'} <PlatformIcon platform={row.platform} /></span>{safeUrl(row.video_url, '') && <a className="v2-button secondary compact v2-league-watch-link" href={safeUrl(row.video_url)} target="_blank" rel="noopener noreferrer">{weekly ? 'View edit' : 'View latest edit'}<ArrowUpRight size={12} aria-hidden="true" /></a>}{row.state && ['pending', 'pending_validation', 'data_pending', 'invalid', 'disqualified'].includes(row.state) && <span className="v2-league-editor-channel">{leagueStateLabel(row.state)}</span>}{weekly && <span className="v2-league-mobile-score">{scoreLabel(row.weekly_score)}</span>}{!weekly && row.latest_result && <span className="v2-league-mobile-latest" title={row.latest_result.period_label}>Latest: {row.latest_result.rank ? `#${row.latest_result.rank}` : "—"} · {pointsLabel(row.latest_result.points)} pts</span>}</div></div></th>{weekly && <td className="v2-league-score-cell"><strong>{leagueNumber(row.weekly_score)?.toFixed(2) ?? '—'}</strong><span>{leagueNumber(row.weekly_score) === null ? 'Awaiting data' : 'Edit score'}</span></td>}{hasLatest && <td className="v2-league-latest-cell">{row.latest_result ? <><strong>{row.latest_result.rank ? `#${row.latest_result.rank}` : '—'} <span>· {pointsLabel(row.latest_result.points)} pts</span></strong><span>{row.latest_result.period_label}</span></> : <span>Awaiting result</span>}</td>}<td className="v2-league-points-cell"><strong>{pointsLabel(weekly && data.provisional ? row.projected_points : row.points)}</strong>{weekly && data.provisional && <span>{leagueNumber(row.projected_points) === null ? 'Awaiting data' : 'Projected'}</span>}{!weekly && row.scored_rounds !== undefined && <span>{row.scored_rounds} {row.scored_rounds === 1 ? 'round' : 'rounds'}</span>}</td>{hasMovement && <td className="v2-league-movement-cell">{typeof row.rank_change === 'number' ? <span aria-label={row.rank_change > 0 ? `Up ${row.rank_change} places` : row.rank_change < 0 ? `Down ${Math.abs(row.rank_change)} places` : 'Unchanged'}>{row.rank_change > 0 ? <ArrowUp size={14} aria-hidden="true" /> : row.rank_change < 0 ? <ArrowDown size={14} aria-hidden="true" /> : '—'}{row.rank_change !== 0 && Math.abs(row.rank_change)}</span> : <span aria-label="Rank change unavailable">—</span>}</td>}{weekly && <td className="v2-league-details-cell"><button type="button" aria-label={`${expanded === row.editor_id ? 'Hide' : 'Show'} score breakdown for ${row.username}`} aria-expanded={expanded === row.editor_id} aria-controls={`${rowId}-${row.editor_id}`} onClick={() => setExpanded(expanded === row.editor_id ? null : row.editor_id)}><ChevronDown size={18} aria-hidden="true" /></button></td>}</tr>{weekly && expanded === row.editor_id && <tr className="v2-league-expanded-row"><td colSpan={columns}><div id={`${rowId}-${row.editor_id}`}><h4>{row.username} · score breakdown</h4><ScoreBreakdown score={row} /></div></td></tr>}</Fragment>)}
      {!rows.length && <tr><td colSpan={columns} className="v2-league-empty-cell">{data.rows.length ? <div className="v2-league-empty-results"><Search size={27} aria-hidden="true" /><h4>No matching editors</h4><p>Try another name, channel, or platform.</p><button className="v2-button secondary compact" type="button" onClick={() => { onSearch(''); onPlatform(''); }}>Clear filters</button></div> : <div className="v2-league-empty-results"><Trophy size={30} aria-hidden="true" /><h4>{neutralTitle}</h4><p>{data.state === 'exhibition' ? 'Exhibition rounds award no official positions or league points.' : ['canceled', 'cancelled'].includes(data.state) ? 'No official points were awarded for this round.' : unavailableFinal ? 'No official results are currently available for this round.' : 'Results will appear after scoring. Every position here is earned through league competition.'}</p><a className="v2-button secondary compact" href="#league-entry">Explore the competition<ArrowUpRight size={15} aria-hidden="true" /></a></div>}</td></tr>}
    </tbody></table></div>
    <div className="v2-league-results-footnote"><span>{weekly ? data.provisional ? 'Projected league points follow current positions and may change. Only finalized awards count toward monthly and all-time totals.' : 'Edit score / 100 → placement → league points.' : data.period === 'all_time' ? 'All finalized V2 weekly point awards across every month and year. Monthly totals are not counted twice; legacy follower scores are excluded.' : 'League points from finalized qualifying rounds only.'}</span>{data.result_revision !== undefined && data.result_revision > 0 && <span>Revision {data.result_revision}</span>}</div>
    {weekly && data.provisional && data.rows.length > 0 && data.minimum_entries && data.rows.length < data.minimum_entries && <p className="v2-small v2-muted v2-league-results-footnote">Projections assume a qualifying round: {data.rows.length} of {data.minimum_entries} required entries are currently listed. Exhibition rounds award no points.</p>}
    {(stateMessage || data.reason) && <details className="v2-league-result-explainer"><summary>About these results</summary>{stateMessage && <p>{stateMessage}</p>}{data.reason && <p>{data.reason}</p>}</details>}
  </div>;
}

function EditorAvatar({ row }: { row: HubStanding }) {
  const [failed, setFailed] = useState(false);
  const src = safeUrl(row.profile_picture, '');
  return <span className="v2-league-editor-avatar" aria-hidden="true">{src && !failed ? <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} /> : row.username.slice(0, 2).toUpperCase()}</span>;
}

export function ScoreBreakdown({ score }: { score: LeagueScore }) {
  const revised = score.scoring_method === 'round_cohort_v2';
  const component = leagueNumber(score.improvement_score);
  const weight = leagueNumber(score.improvement_weight);
  const labels = [{ key: 'response_score', label: 'Like rate' }, { key: 'improvement_score', label: revised ? 'Website performance' : 'Relative performance' }, { key: 'popularity_score', label: score.popularity_metric === 'views' ? 'Total views' : 'Total likes' }] as const;
  return <div className="v2-league-score-breakdown">
    {labels.map(item => { const number = leagueNumber(score[item.key]); return <div className="v2-league-score-component" key={item.key}><div><span>{item.label}</span><strong>{number === null ? 'Awaiting data' : `${number.toFixed(2)} / 100`}</strong></div>{number !== null && <progress value={number} max={100} aria-label={`${item.label}: ${number.toFixed(2)} out of 100`} />}</div>; })}
    {score.debut_bonus && <p className="v2-small"><strong>Debut · first competition week only.</strong> Your performance component is {component ?? '—'}/100{component !== null && weight !== null ? `, contributing ${(component * weight).toFixed(1)} to your overall edit score at a ${Math.round(weight * 100)}% weight` : ''}. This bonus does not repeat in a new month and adds no extra league points.</p>}
    {revised && !score.debut_bonus && score.baseline_sample_count != null && score.baseline_sample_count > 0 && <p className="v2-small v2-muted">History: {score.baseline_sample_count} previous finalized website {score.baseline_sample_count === 1 ? 'edit' : 'edits'} · median {pointsLabel(score.baseline_median_likes)} likes. Current edit: {pointsLabel(score.likes)} likes. Relative performance: {leagueNumber(score.relative_performance)?.toFixed(2) ?? '—'}× (capped at 5×), compared with other returning editors in this round.</p>}
    {score.neutral_baseline && <p className="v2-small v2-muted">{revised ? 'No usable finalized website history was available when the week started. As a returning editor, the performance component is neutral at 50/100; the debut bonus does not repeat.' : 'Relative performance uses the neutral 50/100 score because fewer than five valid, comparable-age videos were available. The entry remains eligible.'}</p>}
    {revised && <p className="v2-small v2-muted">Snapshot: {pointsLabel(score.likes)} likes · {pointsLabel(score.views)} lifetime views. Like rate and views are compared within this round; component scores are not raw engagement percentages.</p>}
    <p className="v2-small v2-muted">Metrics updated: <LocalTime value={score.last_refresh} fallback="No valid snapshot yet" /></p>
  </div>;
}

export function ChannelEligibilityNotice({ applications = [] }: { applications?: OwnLeagueEntries['channel_applications'] }) {
  if (!applications.length) return <Notice>A verified channel is required before you can enter. <a href="/editing-hub/apply">Apply as an editor →</a></Notice>;
  return <Notice><strong>Your channel application</strong>{applications.map(item => {
    const confirmation = !item.removal_requested && !item.channel_verified && ['pending', 'accepted'].includes(item.status);
    const message = item.removal_requested ? 'Removal requested. This channel cannot enter while that request is active.'
      : item.status === 'accepted' && !item.channel_verified ? 'Approved — confirm that this channel belongs to you to unlock entry. You do not need to apply again.'
      : item.status === 'pending' ? (confirmation ? 'Confirm your channel to send the application for review.' : 'Your application is under review. You do not need to apply again.')
      : item.status === 'rejected' ? 'Your application was not approved. Open it for the next steps.' : 'Open your application to check its eligibility.';
    return <div key={item.id}><p>{item.channel_name || platformLabel(item.platform)}: {message}</p><a className="v2-arrow-link" href={`/applications/editors/${item.id}`}>{confirmation ? 'Confirm your channel' : 'View application'} →</a></div>;
  })}</Notice>;
}

function YourEntries({ status, onChange }: { status: LeagueStatus | null; onChange: () => void }) {
  const { user, sessionLoading, sessionError } = useSite();
  const entries = useLeagueResource<OwnLeagueEntries>(user ? 'league/entries/me/' : null);
  const [message, setMessage] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  function changed(text: string) { setMessage(text); setEditing(null); setConfirming(null); entries.reload(); onChange(); }
  async function withdraw(entry: LeagueEntry) {
    setBusy(entry.id); setError(null); setMessage('');
    try { await mutate(`league/entries/${entry.id}/withdraw/`); changed('Your entry has been withdrawn.'); }
    catch (error) { setError(error as Error); entries.reload(); }
    finally { setBusy(null); }
  }
  if (sessionLoading) return <Loading label="Checking your account…" />;
  if (sessionError) return <ErrorNotice error={sessionError} retry={() => window.location.reload()} />;
  if (!user) return <Notice><a href="/login?next=/editing-hub">Sign in</a> to submit an edit and manage your entries.</Notice>;
  const nextEntry = status?.next_week ? entries.data?.entries.find(entry => entry.week.id === status.next_week?.id && entry.state !== 'withdrawn') : null;
  const maySubmit = status ? canEnterLeague(status) : false;
  return <div className="v2-stack"><ErrorNotice error={entries.error} retry={entries.reload} /><ErrorNotice error={error} />{message && <Notice>{message}</Notice>}{entries.loading && !entries.data && <Loading label="Loading your entries…" />}{entries.data && <>
    {!status ? <Notice>Competition status is unavailable. Entry changes will be available once it can be checked.</Notice> : !maySubmit ? <Notice>{!status.enabled ? 'Submissions are not open yet.' : !status.configuration_ready ? 'Submissions will open when league calibration is ready.' : 'There is no open intake at the moment.'}{status.reason && ` ${status.reason}`}</Notice> : !entries.data.verified_channels.length ? <ChannelEligibilityNotice applications={entries.data.channel_applications} /> : !nextEntry && <section className="v2-panel"><h3>Enter the next round</h3><ScheduledWeek week={status.next_week!} /><EntryForm channels={entries.data.verified_channels} onSuccess={() => changed('Your edit has been submitted for the next round. Its validation status is shown below.')} /></section>}
    {entries.data.entries.length ? entries.data.entries.map(entry => <article id={`entry-${entry.id}`} key={entry.id} className="v2-panel v2-league-own-entry"><div className="v2-section-heading"><div><span className="v2-eyebrow">{entry.platform}</span><h3>{entry.title || 'Your submitted edit'}</h3>{entry.debut_bonus && <span className="v2-league-you">Debut · first competition week</span>}</div><span className="v2-pill">{leagueStateLabel(entry.state)}</span></div><ScheduledWeek week={entry.week} />{safeUrl(entry.video_url, '') && <a className="v2-arrow-link" href={safeUrl(entry.video_url)} target="_blank" rel="noopener noreferrer">View your edit ↗</a>}{entry.validation_message && <Notice>{entry.validation_message}</Notice>}
      <div className="v2-league-entry-result"><div><span>Edit score</span><strong>{scoreLabel(entry.weekly_score)}</strong></div><div><span>League points</span><strong>{pointsLabel(entry.points)}</strong></div></div>{leagueNumber(entry.weekly_score) !== null && <details className="v2-league-breakdown"><summary>View your score breakdown</summary><ScoreBreakdown score={entry} /></details>}
      <div className="v2-actions">{entry.can_replace && <button type="button" className="v2-button secondary compact" disabled={!status?.enabled || busy !== null} onClick={() => { setEditing(editing === entry.id ? null : entry.id); setConfirming(null); }}>{editing === entry.id ? 'Cancel replacement' : 'Replace edit'}</button>}{entry.can_withdraw && <button type="button" className="v2-text-button" disabled={!status?.enabled || busy !== null} onClick={() => { setConfirming(entry.id); setEditing(null); }}>Withdraw entry</button>}</div>
      {!entry.can_replace && !entry.can_withdraw && !['withdrawn', 'invalid', 'disqualified'].includes(entry.state) && <p className="v2-small v2-muted">This entry is locked. Changes require a recorded moderation decision.</p>}
      {editing === entry.id && entry.can_replace && <EntryForm entry={entry} channels={entries.data!.verified_channels} onSuccess={() => changed('Your scheduled entry has been replaced.')} />}
      {confirming === entry.id && entry.can_withdraw && <Notice>Withdraw this entry from {entry.week.label}?<div className="v2-actions"><button type="button" className="v2-button secondary compact" disabled={busy !== null} onClick={() => setConfirming(null)}>Keep entry</button><button type="button" className="v2-button compact" disabled={busy !== null} onClick={() => withdraw(entry)}>{busy === entry.id ? 'Withdrawing…' : 'Confirm withdrawal'}</button></div></Notice>}
    </article>) : <p className="v2-muted">You have no league entries yet.</p>}
  </>}</div>;
}

function ScheduledWeek({ week }: { week: LeagueWeek }) {
  return <div className="v2-league-scheduled">{week.scoring_method === 'round_cohort_v2' && <p className="v2-small v2-muted">This round uses total views and up to five finalized website edits for performance history. First-time competitors receive a {pointsLabel(week.debut_improvement_score)}/100 debut performance component.</p>}<p><strong>Target competition: {week.label}.</strong></p>{week.competition_month && <p>League month: {week.competition_month} (Friday cutoff).</p>}<p>Scoring starts <LocalTime value={week.starts_at} />. Cutoff: <LocalTime value={week.cutoff_at} />.</p><p>Submission, replacement and withdrawal deadline: <LocalTime value={week.starts_at} />.</p></div>;
}
function EntryForm({ channels, entry, onSuccess }: { channels: VerifiedLeagueChannel[]; entry?: LeagueEntry; onSuccess: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const hint = useId();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    const form = event.currentTarget;
    const values = new FormData(form);
    try {
      await mutate(entry ? `league/entries/${entry.id}/replace/` : 'league/entries/', { video_url: String(values.get('video_url') || '').trim(), approved_application_id: Number(values.get('approved_application_id')) });
      form.reset(); onSuccess();
    } catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  return <form className="v2-form v2-league-entry-form" onSubmit={submit}><ErrorNotice error={error} /><fieldset disabled={busy}><Field label="Verified channel"><select name="approved_application_id" required defaultValue={entry?.approved_application_id || (channels.length === 1 ? channels[0].id : '')}><option value="" disabled>Select your channel</option>{channels.map(channel => <option key={channel.id} value={channel.id}>{channel.channel_name || channel.platform} · {channel.platform}</option>)}</select></Field><Field label="YouTube or TikTok video URL"><input name="video_url" type="url" required maxLength={2000} defaultValue={entry?.video_url || ''} placeholder="https://…" aria-describedby={hint} /></Field><p id={hint} className="v2-small v2-muted">Submit a video from the selected verified channel. Older edits are eligible; existing engagement counts. One scoring entry per editor per round, across both platforms.</p><p className="v2-small v2-muted">Each edit can enter once per competition month. We check video identities automatically. The month is determined by the target round’s Friday date.</p><button className="v2-button" type="submit" disabled={busy || channels.length === 0}>{busy ? 'Submitting…' : entry ? 'Replace scheduled entry →' : 'Submit for next round →'}</button></fieldset></form>;
}

export function LeagueRules({ status }: { status: LeagueStatus | null }) {
  const weights = status?.weights;
  const revised = status?.scoring_method === 'round_cohort_v2';
  const automatic = revised || status?.scoring_method === 'round_cohort_v1';
  const percent = (value: string | number | null | undefined) => { const number = leagueNumber(value); return number === null ? 'Not set' : `${Math.round(number * 100)}%`; };
  return <section className="v2-panel v2-league-rules" aria-labelledby="league-rules-title"><span className="v2-eyebrow">Know the competition</span><h2 id="league-rules-title">How your result works</h2><div className="v2-league-rule-grid"><div><h3>Scores and points</h3><p>Audience response, relative performance, and popularity combine into an edit score out of 100. Your placement then earns league points in qualifying rounds.</p><dl className="v2-league-weight-list"><div><dt>Like rate</dt><dd>{weights ? percent(weights.response) : 'Awaiting scoring version'}</dd></div><div><dt>{revised ? 'Website performance' : 'Relative performance'}</dt><dd>{weights ? percent(weights.improvement) : 'Awaiting scoring version'}</dd></div><div><dt>{revised ? 'Total views' : 'Total likes'}</dt><dd>{weights ? percent(weights.popularity) : 'Awaiting scoring version'}</dd></div></dl><p>{automatic ? 'Automatic starter scoring compares real entries in this round. It is not a validated fairness model across platforms or video ages.' : status?.configuration_ready ? 'Weights belong to the configured scoring version.' : 'These are proposed weights; real provider calibration is still required.'}</p><p>Placement points: {status?.placement_points?.length ? status.placement_points.join(', ') : '25, 20, 16, 13, 11, 10, 9, 8, 7, 6'} for places 1–10; other eligible finishers earn {status?.finisher_points ?? 2}. Missing or disqualified entries earn 0. No points are awarded while required data remains unresolved.</p></div><div><h3>A shared weekly clock</h3><p>Entries submitted during a calendar week join the following round. Scoring runs Monday through Friday in UTC. The weekend displays frozen results, or a clearly labeled pending result if required data is missing.</p><p>Each underlying edit can enter once per competition month, and may enter again in a later month. Canonical video IDs and reviewed cross-post matches are checked; reuploads cannot always be detected automatically and may require moderation. Your entry locks when its round starts.</p></div><div><h3>Older edits belong here</h3><p>Your video’s lifetime likes and views count, including engagement before submission. {revised ? 'Like rate compares lifetime likes divided by views. Total views supplies the popularity component. Performance compares current likes with the median likes of your last one to five distinct finalized website edits, using saved results from before this week started. No channel-wide history is fetched. The likes ratio is capped at 5× and ranked against returning editors in this round.' : automatic ? 'Audience response compares like-to-view rates, popularity compares lifetime likes, and relative performance compares improvement against available creator history. Component positions are scaled within this round; older edits and platforms are not independently normalized.' : 'Comparisons use the same platform, video format, and a comparable video age.'}</p>{revised ? <p><strong>Debut:</strong> your first competition week uses {pointsLabel(status?.debut_improvement_score)}/100 for the performance component. Later weeks use your available website history, up to five edits; returning editors without usable history receive neutral 50/100. The debut bonus never repeats each month. It changes your edit score, not the placement points schedule. Each measured component uses mid-rank percentiles: highest 100, lowest 0, ties share a score; a single comparable entry gets 50.</p> : <p>If fewer than five trustworthy comparison videos are available, relative performance uses a neutral 50/100. The other components still count.</p>}{status?.minimum_entries != null && <p>A round needs {status.minimum_entries} eligible {status.minimum_entries === 1 ? 'entry' : 'entries'} to award league points. Smaller rounds are exhibitions.</p>}</div><div><h3>A fresh league every month</h3><p>Each calendar month is a fresh league. Join any time at zero monthly points, with no catch-up bonus. Every finalized round counts toward the month containing its Friday scoring date. Previous results and achievements stay archived.</p><p>The monthly winner is the editor with the strongest accumulated result. The featured monthly video represents that editor’s best eligible edit from that month.</p></div></div></section>;
}
