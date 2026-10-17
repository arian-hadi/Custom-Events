import type { Notification } from './api';
import type { LeagueNumber, LeagueWeek } from './league-view';
import { paymentStatusLabel } from './commerce';

export type EditorApplicationSummary = {
  id: number | null;
  platform: string;
  status: string;
  channel_name: string;
  channel_verified: boolean;
  removal_requested: boolean;
  applied_at: string | null;
  updated_at: string | null;
  url: string;
};

export type MemberDashboard = {
  generated_at: string;
  member: {
    id: number; username: string; display_name: string; profile_picture: string | null;
    editor_title: string; editor_title_rarity?: string | null; verified_editor: boolean; verified_platforms: string[];
  };
  league: {
    enabled: boolean; configuration_ready: boolean; can_submit: boolean; reason: string;
    month: { label: string; rank: number | null; points: LeagueNumber; scored_rounds: number };
    current_week: LeagueWeek | null; next_week: LeagueWeek | null; submission_deadline: string | null;
    current_entry: DashboardEntry | null; next_entry: DashboardEntry | null;
    latest_result: {
      entry_id: number; title: string; rank: number | null; points: LeagueNumber;
      weekly_score: LeagueNumber; period_label: string; scored_at: string | null; video_url: string;
    } | null;
    rank_change: number | null;
  };
  latest_edit: {
    id: number; source: 'league' | 'legacy'; title: string; video_url: string;
    thumbnail: string | null; platform: string; submitted_at: string; state: string;
    rank: number | null; league_points: LeagueNumber; upvotes: number | null; detail_url: string;
  } | null;
  edit_stats: {
    league_submissions: number; legacy_submissions: number; legacy_verified: number;
    legacy_upvotes: number; league_points: LeagueNumber; best_league_result: number | null;
  };
  applications: {
    editors: EditorApplicationSummary[];
    events: { id: number; event_id: number; title: string; status: string; applied_at: string; updated_at: string; url: string }[];
    event_count: number;
  };
  notifications: { unread_count: number; results: Notification[] };
  orders: {
    id: string; product_id: number; product_name: string; display_amount: string; currency: string;
    status: string; fulfillment_status: string; fulfillment_note: string;
    created_at: string; paid_at: string | null; url: string;
  }[];
  favorites_count: number;
};

type DashboardEntry = { id: number; title: string; state: string; video_url: string; detail_url: string };
export type DashboardAttention = { key: string; label: string; detail: string; href: string; urgent?: boolean };

export function applicationStatus(status: string): string {
  return ({ accepted: 'Approved', approved: 'Approved', pending: 'Under review', rejected: 'Rejected', not_applied: 'Not applied', withdrawn: 'Withdrawn' } as Record<string, string>)[status] || status.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
}

export function submissionDeadline(value: string | null, now: string): string | null {
  if (!value) return null;
  const remaining = Date.parse(value) - Date.parse(now);
  if (!Number.isFinite(remaining)) return null;
  if (remaining <= 0) return 'Entry deadline passed';
  const minutes = Math.ceil(remaining / 60000);
  if (minutes >= 1440) { const days = Math.ceil(minutes / 1440); return `Closes in ${days} ${days === 1 ? 'day' : 'days'}`; }
  if (minutes >= 60) { const hours = Math.ceil(minutes / 60); return `Closes in ${hours} ${hours === 1 ? 'hour' : 'hours'}`; }
  return `Closes in ${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`;
}

export function dashboardAttention(data: MemberDashboard): DashboardAttention[] {
  const items: DashboardAttention[] = [];
  const league = data.league;
  const deadline = submissionDeadline(league.submission_deadline, data.generated_at);
  if (league.enabled && league.configuration_ready && league.can_submit && data.member.verified_editor && deadline) {
    items.push({ key: 'competition', label: league.next_entry ? 'Your next entry' : 'Next competition', detail: league.next_entry ? `Submitted · ${deadline.toLowerCase()}` : deadline, href: '/editing-hub#league-entry', urgent: !league.next_entry });
  }
  for (const application of data.applications.editors) {
    if (application.status === 'pending' || application.removal_requested) items.push({ key: `editor-${application.platform}`, label: `${application.platform === 'youtube' ? 'YouTube' : application.platform === 'tiktok' ? 'TikTok' : application.platform} editor`, detail: application.removal_requested ? 'Removal request pending' : application.channel_verified ? 'Application under review' : 'Confirm your channel to submit', href: application.url });
  }
  if (data.notifications.unread_count) items.push({ key: 'notifications', label: 'Unread notifications', detail: `${data.notifications.unread_count} ${data.notifications.unread_count === 1 ? 'update' : 'updates'} to read`, href: '/notifications' });
  const pendingOrder = data.orders.find(order => ['failed', 'review_required', 'pending', 'creating', 'processing', 'open'].includes(order.status));
  if (pendingOrder) items.push({ key: 'order', label: `Order #${pendingOrder.id.length > 12 ? `${pendingOrder.id.slice(0, 8)}…` : pendingOrder.id}`, detail: paymentStatusLabel(pendingOrder.status), href: pendingOrder.url });
  const recentEvent = data.applications.events.find(application => {
    const age = Date.parse(data.generated_at) - Date.parse(application.updated_at);
    return application.status === 'pending' || (Number.isFinite(age) && age >= 0 && age < 14 * 86400000);
  });
  if (recentEvent) items.push({ key: 'event', label: recentEvent.title, detail: `Event application · ${applicationStatus(recentEvent.status).toLowerCase()}`, href: recentEvent.url });
  return items.slice(0, 4);
}
