/** League display values stay separate from scoring, which is authoritative in Django. */
export type LeagueNumber = string | number | null | undefined;
export type LeaguePeriod = 'week' | 'month' | 'all_time';

export type LeagueWeek = {
  scoring_method?: string;
  debut_improvement_score?: LeagueNumber;
  competition_month?: string;
  id: number;
  label: string;
  starts_at: string;
  cutoff_at: string;
  ends_at?: string;
  state: string;
  last_refresh?: string | null;
  result_revision?: number;
  calendar_year?: number;
  entry_count?: number;
  official_results?: boolean;
};
export type LeagueRounds = {
  years: { id: number; year: number; name: string }[];
  selected_year: number;
  rounds: LeagueWeek[];
  current_week_id: number | null;
  next_week_id: number | null;
};
export type LeagueStatus = {
  debut_improvement_score?: LeagueNumber;
  scoring_method?: string | null;
  scoring_validated?: boolean;
  placement_points?: number[];
  finisher_points?: number | null;
  minimum_entries?: number | null;
  enabled: boolean;
  configuration_ready: boolean;
  can_submit?: boolean;
  reason?: string;
  current_week: LeagueWeek | null;
  next_week: LeagueWeek | null;
  month: { month: number; name: string; year: number };
  last_refresh: string | null;
  weights?: { response: LeagueNumber; improvement: LeagueNumber; popularity: LeagueNumber };
};
export type LeagueScore = {
  scoring_method?: string;
  popularity_metric?: 'views' | 'likes';
  baseline_policy?: string;
  baseline_sample_count?: number | null;
  baseline_median_likes?: LeagueNumber;
  relative_performance?: LeagueNumber;
  likes?: LeagueNumber;
  views?: LeagueNumber;
  debut_bonus?: boolean;
  improvement_weight?: LeagueNumber;
  weekly_score?: LeagueNumber;
  response_score?: LeagueNumber;
  improvement_score?: LeagueNumber;
  popularity_score?: LeagueNumber;
  neutral_baseline?: boolean;
  last_refresh?: string | null;
};
export type LeagueStanding = LeagueScore & {
  editor_title?: string;
  editor_title_rarity?: string | null;
  editor_id: number;
  username: string;
  rank: number | null;
  points: LeagueNumber;
  projected_points?: LeagueNumber;
  entry_id?: number | null;
  video_url?: string;
  state?: string;
  platform?: string;
  channel_name?: string | null;
  channel_verified?: boolean;
  profile_picture?: string | null;
  scored_rounds?: number;
  latest_result?: { rank: number | null; points: LeagueNumber; period_label: string } | null;
  rank_change?: number | null;
};
export type LeagueStandings = {
  period: LeaguePeriod;
  period_label: string;
  state: string;
  provisional: boolean;
  rows: LeagueStanding[];
  last_refresh?: string | null;
  result_revision?: number;
  reason?: string;
  minimum_entries?: number;
};
export type LeagueWinner = {
  editor_title?: string;
  editor_title_rarity?: string | null;
  platform?: string;
  video_format?: string;
  username: string;
  title: string;
  video_url: string;
  period_label: string;
  points: LeagueNumber;
  weekly_score: LeagueNumber;
  result_revision?: number;
};
export type LeagueWinners = {
  weekly_winner: LeagueWinner | null;
  monthly_winner: LeagueWinner | null;
  weekly_state?: string;
  monthly_state?: string;
};
export type VerifiedLeagueChannel = { id: number; platform: string; channel_name: string; channel_url?: string };
export type LeagueEntry = LeagueScore & {
  id: number;
  title?: string;
  video_url: string;
  platform: string;
  state: string;
  week: LeagueWeek;
  approved_application_id?: number;
  points?: LeagueNumber;
  can_replace: boolean;
  can_withdraw: boolean;
  validation_message?: string;
};
export type LeagueChannelApplication = { id: number; platform: string; channel_name: string; status: string; channel_verified: boolean; removal_requested: boolean; url: string };
export type OwnLeagueEntries = { entries: LeagueEntry[]; verified_channels: VerifiedLeagueChannel[]; channel_applications?: LeagueChannelApplication[] };

export function leagueNumber(value: LeagueNumber): number | null {
  // Missing values must never become an invented zero, including empty strings.
  if (value === null || value === undefined || (typeof value === 'string' && !value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
export function scoreLabel(value: LeagueNumber): string {
  const number = leagueNumber(value);
  return number === null ? 'Awaiting score' : `${number.toFixed(2)} / 100`;
}
export function pointsLabel(value: LeagueNumber): string {
  const number = leagueNumber(value);
  return number === null ? '—' : new Intl.NumberFormat('en', { maximumFractionDigits: 2 }).format(number);
}
export function leagueStateLabel(state?: string): string {
  const labels: Record<string, string> = {
    disabled: 'Not open', scheduled: 'Scheduled', queued: 'Scheduled', live: 'Provisional', active: 'Provisional',
    finalizing: 'Results pending', data_pending: 'Data pending', finalized: 'Finalized', frozen: 'Frozen',
    exhibition: 'Exhibition', canceled: 'Canceled', cancelled: 'Canceled', corrected: 'Corrected results',
    withdrawn: 'Withdrawn', invalid: 'Ineligible', disqualified: 'Disqualified', pending: 'Validation pending',
    pending_validation: 'Validation pending', eligible: 'Eligible', calibration_pending: 'Calibration pending',
  };
  return state ? labels[state] || state.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase()) : 'Awaiting update';
}
export function leagueStateMessage(state?: string): string {
  const messages: Record<string, string> = {
    scheduled: 'This round has not started. Its standings will appear when scoring begins.',
    live: 'Standings are provisional until the round is finalized. Scores use existing lifetime likes and views.',
    active: 'Standings are provisional until the round is finalized. Scores use existing lifetime likes and views.',
    data_pending: 'Some required metrics are unavailable. Missing data is not counted as zero, and official results are pending.',
    finalizing: 'The scoring window has closed. Results are pending validation; later engagement will not change the closing snapshot.',
    finalized: 'These results are frozen. Only a recorded administrative correction can revise them.',
    frozen: 'These results are frozen. Later likes and views do not change the result.',
    corrected: 'A recorded correction has revised these results.',
    exhibition: 'This is an exhibition round. It awards no league points or official weekly winner.',
    canceled: 'This round was canceled and awards no league points.',
    cancelled: 'This round was canceled and awards no league points.',
    calibration_pending: 'Official scoring is waiting for validated platform and video-age comparisons.',
  };
  return messages[state || ''] || '';
}
export function canEnterLeague(status: LeagueStatus): boolean {
  // The browser never unlocks submissions based on its own clock.
  return status.enabled && status.configuration_ready && status.can_submit === true && status.next_week !== null;
}
export function cutoffCountdown(cutoff: string | null | undefined, now: number): string | null {
  if (!cutoff) return null;
  const end = Date.parse(cutoff);
  if (!Number.isFinite(end)) return null;
  if (end <= now) return 'Scoring window ended';
  const minutes = Math.ceil((end - now) / 60000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const remainder = minutes % 60;
  return `${days ? `${days}d ` : ''}${hours}h ${remainder}m until cutoff`;
}
