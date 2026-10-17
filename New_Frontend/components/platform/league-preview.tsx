'use client';

import { useState } from 'react';
import { useResource } from '@/lib/api';
import type { HubStandings } from '@/lib/league-presentation';
import type { LeagueWinner } from '@/lib/league-view';
import { Standings, WinnerCard } from './league';
import { ErrorNotice, Loading, Notice, PageHeading } from './ui';

type Preview = {
  preview: true; state: string; simulated_at: string; week_label: string; starts_at: string; cutoff_at: string;
  month_label: string; weekly: HubStandings; monthly: HubStandings; all_time: HubStandings; weekly_winner: LeagueWinner; monthly_winner: LeagueWinner;
};
const states = [{ value: 'live', label: 'Live weekday' }, { value: 'frozen', label: 'Frozen weekend' }, { value: 'pending', label: 'Missing closing data' }];

export function LeaguePreviewPage({ token, initialState = 'live' }: { token: string; initialState?: string }) {
  const [state, setState] = useState(states.some(item => item.value === initialState) ? initialState : 'live');
  const [period, setPeriod] = useState<'week' | 'month' | 'all_time'>('week');
  const [search, setSearch] = useState('');
  const [platform, setPlatform] = useState('');
  const resource = useResource<Preview>(token ? `league/preview/?${new URLSearchParams({ token, state })}` : null);
  const data = resource.data;
  return <div className="v2-container v2-page v2-league-page">
    <PageHeading eyebrow="Local preview · Sample data" title="Weekly league preview"><p>Explore how an active competition looks. These fictional editors, scores and awards never enter the real league.</p></PageHeading>
    <Notice>This is a visual preview. Real submissions, schedules, emails and points remain unchanged. <a href="/editing-hub">Return to the actual Editing Hub →</a></Notice>
    {!token ? <Notice error>Run the league_preview command and open the link it prints. Preview links expire after two hours.</Notice> : <>
      <div className="v2-actions" role="group" aria-label="Preview scenario">{states.map(item => <button key={item.value} className={`v2-button compact${state === item.value ? '' : ' secondary'}`} aria-pressed={state === item.value} onClick={() => setState(item.value)}>{item.label}</button>)}</div>
      <ErrorNotice error={resource.error} retry={resource.reload} />{resource.loading && <Loading label="Loading sample competition…" />}
      {data && <>
        <section className="v2-panel"><span className="v2-eyebrow">Simulated competition</span><h2>{data.week_label}</h2><p>Preview clock: {new Date(data.simulated_at).toUTCString()}</p><p>Friday cutoff: {new Date(data.cutoff_at).toUTCString()} · League month: {data.month_label}</p><p className="v2-muted">{data.state === 'live' ? 'Live edit scores and projected league points are visible. This round has not awarded league points yet.' : data.state === 'frozen' ? 'Frozen sample results show final positions, placement points and one weekly winner.' : 'One sample provider observation is missing. Finalization and this round’s league points wait for valid closing data.'}</p></section>
        <section id="league-standings" className="v2-section"><h2>Sample standings</h2><div className="v2-league-periods" role="group" aria-label="Standings period"><button aria-pressed={period === 'week'} className={period === 'week' ? 'active' : ''} onClick={() => setPeriod('week')}>Weekly league</button><button aria-pressed={period === 'month'} className={period === 'month' ? 'active' : ''} onClick={() => setPeriod('month')}>Monthly league</button><button aria-pressed={period === 'all_time'} className={period === 'all_time' ? 'active' : ''} onClick={() => setPeriod('all_time')}>All-time points</button></div><Standings data={period === 'week' ? data.weekly : period === 'month' ? data.monthly : data.all_time} search={search} platform={platform} onSearch={setSearch} onPlatform={setPlatform} /></section>
        <section className="v2-two-columns v2-league-showcases" aria-label="Sample winner cards"><WinnerCard title="Edit of the Week" winner={data.weekly_winner} monthly={false} state={data.weekly.state} loading={false} error={null} retry={resource.reload} /><WinnerCard title="Editor of the Month" winner={data.monthly_winner} monthly state="finalized" loading={false} error={null} retry={resource.reload} /></section>
        <section id="league-entry" className="v2-section"><Notice>Preview only: entry submission is disabled here. Use the actual Editing Hub to manage real entries. Sample scores illustrate the layout; they are not provider observations or scoring-validation evidence.</Notice></section>
      </>}
    </>}
  </div>;
}
