import type { LeaguePeriod, LeagueStanding, LeagueStandings, LeagueWeek } from './league-view';

/** Additive presentation fields. Django remains the source of positions and points. */
export type HubStanding = LeagueStanding & {
  platform?: string;
  channel_name?: string;
  channel_verified?: boolean;
  profile_picture?: string | null;
  scored_rounds?: number;
  latest_result?: { rank: number | null; points: string | number | null; period_label: string } | null;
  rank_change?: number | null;
};
export type HubStandings = Omit<LeagueStandings, 'rows'> & { rows: HubStanding[] };
export type HubRound = LeagueWeek & { entry_count?: number; calendar_year?: number; official_results?: boolean };
export type LeagueRounds = {
  years: { id: number; year: number; name: string }[];
  selected_year: number;
  months?: { month: number; label: string }[];
  rounds: HubRound[];
  current_week_id?: number | null;
  next_week_id?: number | null;
};

export function filterStandings(rows: HubStanding[], search: string, platform = ''): HubStanding[] {
  const term = search.trim().toLocaleLowerCase('en');
  // Preserve the published order and position, including ties, after filtering.
  return rows.filter(row => (!platform || row.platform === platform)
    && (!term || `${row.username} ${row.channel_name || ''}`.toLocaleLowerCase('en').includes(term)));
}

export function standingsPath(period: LeaguePeriod, year: string, month: string, week: string): string {
  const query = new URLSearchParams({ period });
  if (period === 'week') { if (week) query.set('week', week); }
  else if (period === 'month') {
    if (year) query.set('year', year);
    if (period === 'month' && month) query.set('month', month);
  }
  return `league/standings/?${query}`;
}

export function standingsStatus(data: Pick<LeagueStandings, 'period' | 'provisional' | 'state'> & { rows?: LeagueStanding[] }): string {
  if (data.period === 'all_time') return 'All finalized weekly points · across every month';
  if (data.period === 'month') {
    if (data.state === 'finalizing') return 'Month results pending';
    return data.state === 'finalized' ? 'Finalized monthly standings' : 'Finalized round points';
  }
  if (data.state === 'exhibition') return 'Exhibition · no league points';
  if (data.state === 'canceled' || data.state === 'cancelled') return 'Round canceled';
  if (data.state === 'finalized' || data.state === 'corrected') return data.rows?.length === 0 ? 'No official results available' : 'Official result';
  if (data.state === 'finalizing' || data.state === 'data_pending') return 'Results pending';
  return data.provisional ? 'Provisional standings' : 'Results pending';
}

export function platformLabel(value?: string): string {
  if (value === 'youtube') return 'YouTube';
  if (value === 'tiktok') return 'TikTok';
  return value || 'Editor';
}


export function browsableRounds(data?: LeagueRounds | null) {
  return data?.rounds.filter(round => round.state !== 'scheduled') || [];
}
