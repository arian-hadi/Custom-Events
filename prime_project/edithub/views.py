from collections import defaultdict

from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, DetailView
from django.db.models import Q
from django.core.paginator import Paginator
from .models import EditorApplication, EditSubmission, EditUpvote, EditReport, Tournament, TournamentMatchVote
from .forms import EditorApplicationForm, EditSubmissionForm, EditReportForm
from .utils import (
    fetch_youtube_channel_data,
    fetch_tiktok_channel_data,
    validate_channel_url,
    get_competition_state,
    format_countdown,
    get_week_start_end,
)
from accounts.models import CustomUser
from datetime import datetime, timedelta, timezone
import json
import logging

logger = logging.getLogger(__name__)


class RankingTableView(ListView):
    """Public ranking table view - FIFA World Cup style"""
    model = EditorApplication
    template_name = 'edithub/ranking_table.html'
    context_object_name = 'rankings'
    paginate_by = 50
    
    def get_queryset(self):
        # Only show accepted applications that haven't been removed
        base_queryset = EditorApplication.objects.filter(
            status='accepted',
            removal_requested=False
        ).select_related('user').order_by('-follower_count', 'applied_date')
        
        # Filter by search query if provided
        search_query = self.request.GET.get('q', '').strip()
        if search_query:
            base_queryset = base_queryset.filter(
                Q(channel_name__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )
        self.search_query = search_query
        
        # Filter by editing area if provided
        editing_area = self.request.GET.get('editing_area')
        if editing_area:
            base_queryset = base_queryset.filter(
                Q(editing_area=editing_area) | Q(editing_area='all')
            )
        self.selected_area = editing_area or ''

        # Default to 'mix' if search query is present and no channel_filter specified
        # If search is present without explicit channel_filter, default to mix
        channel_filter = self.request.GET.get('channel_filter', '').lower()
        if search_query and not channel_filter:
            channel_filter = 'mix'
        elif not channel_filter or channel_filter not in ['mix', 'youtube', 'tiktok']:
            channel_filter = 'mix'

        # Calculate channel counts correctly
        # For mix: count distinct users (not applications)
        mix_user_count = base_queryset.values('user_id').distinct().count()
        youtube_count = base_queryset.filter(channel_type='youtube').count()
        tiktok_count = base_queryset.filter(channel_type='tiktok').count()
        
        self.channel_counts = {
            'mix': mix_user_count,
            'youtube': youtube_count,
            'tiktok': tiktok_count,
        }

        self.mix_queryset = base_queryset
        if channel_filter == 'youtube':
            queryset = base_queryset.filter(channel_type='youtube')
        elif channel_filter == 'tiktok':
            queryset = base_queryset.filter(channel_type='tiktok')
        else:
            queryset = base_queryset

        self.channel_filter = channel_filter
        self.full_queryset = queryset
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['editing_areas'] = EditorApplication.EDITING_AREA_CHOICES
        context['selected_area'] = self.request.GET.get('editing_area', '')
        context['channel_filter'] = getattr(self, 'channel_filter', 'mix')
        # Ensure channel_counts are always available
        if hasattr(self, 'channel_counts'):
            context['channel_counts'] = self.channel_counts
        else:
            # Fallback: calculate if not set
            base_queryset = EditorApplication.objects.filter(
                status='accepted',
                removal_requested=False
            )
            context['channel_counts'] = {
                'mix': base_queryset.values('user_id').distinct().count(),
                'youtube': base_queryset.filter(channel_type='youtube').count(),
                'tiktok': base_queryset.filter(channel_type='tiktok').count(),
            }
        channel_filter = context['channel_filter']
        # If search query is present, automatically show all results
        search_query = getattr(self, 'search_query', '') if hasattr(self, 'search_query') else self.request.GET.get('q', '')
        show_all = self.request.GET.get('all') == '1' or bool(search_query)
        context['show_all'] = show_all
        context['search_query'] = search_query

        if channel_filter == 'mix':
            mix_entries = self._build_mix_entries()

            # current user rank (mix)
            current_user_rank = None
            if self.request.user.is_authenticated:
                for entry in mix_entries:
                    if entry.get('user') == self.request.user:
                        current_user_rank = entry.get('rank')
                        break
            context['current_user_rank'] = current_user_rank

            if show_all:
                paginator = Paginator(mix_entries, self.paginate_by)
                page_number = self.request.GET.get('page')
                page_obj = paginator.get_page(page_number)
                context['rankings'] = page_obj.object_list
                context['object_list'] = page_obj.object_list
                context['page_obj'] = page_obj
                context['is_paginated'] = page_obj.has_other_pages()
                context['paginator'] = paginator
            else:
                context['rankings'] = mix_entries[:5]
                context['object_list'] = mix_entries[:5]
                context['is_paginated'] = False
            context['total_editors'] = len(mix_entries)
        else:
            # For platform-specific rankings, we need to calculate actual ranks from unfiltered data
            # Get unfiltered queryset for the platform
            unfiltered_base = EditorApplication.objects.filter(
                status='accepted',
                removal_requested=False,
                channel_type=channel_filter
            ).select_related('user').order_by('-follower_count', 'applied_date')
            
            # Apply editing area filter if present
            editing_area = getattr(self, 'selected_area', '')
            if editing_area:
                unfiltered_base = unfiltered_base.filter(
                    Q(editing_area=editing_area) | Q(editing_area='all')
                )
            
            # Build list with actual ranks - THIS IS THE SOURCE OF TRUTH
            unfiltered_list = list(unfiltered_base)
            user_rank_map = {}
            for index, app in enumerate(unfiltered_list, start=1):
                user_rank_map[app.user_id] = index
                # Set actual_rank directly on the app object for immediate use
                app.actual_rank = index
            
            # Now get the filtered queryset
            queryset = getattr(self, 'full_queryset', super().get_queryset())
            
            # Add actual ranks to the queryset results
            if search_query:
                # For filtered results, we need to add rank attribute to each object
                queryset_list = list(queryset)
                for app in queryset_list:
                    # Always get from user_rank_map to ensure accuracy
                    app.actual_rank = user_rank_map.get(app.user_id)
                queryset = queryset_list
            
            # current user rank (platform)
            current_user_rank = None
            if self.request.user.is_authenticated:
                current_user_rank = user_rank_map.get(self.request.user.id)
            context['current_user_rank'] = current_user_rank

            if show_all:
                # If we have a list (from search), use it directly; otherwise paginate
                if isinstance(queryset, list):
                    # Ensure actual_rank is set for all items in the list
                    for app in queryset:
                        app.actual_rank = user_rank_map.get(app.user_id)
                        # If somehow not in map, this shouldn't happen but ensure it's set
                        if app.actual_rank is None:
                            logger.warning(f"User {app.user_id} not found in rank map for {channel_filter}")
                            app.actual_rank = 999  # Fallback to high number
                    paginator = Paginator(queryset, self.paginate_by)
                    page_number = self.request.GET.get('page')
                    page_obj = paginator.get_page(page_number)
                    context['rankings'] = page_obj.object_list
                    context['object_list'] = page_obj.object_list
                    context['page_obj'] = page_obj
                    context['is_paginated'] = page_obj.has_other_pages()
                    context['paginator'] = paginator
                else:
                    paginator = Paginator(queryset, self.paginate_by)
                    page_number = self.request.GET.get('page')
                    page_obj = paginator.get_page(page_number)
                    # Add actual ranks to paginated results - CRITICAL: Always use user_rank_map
                    for app in page_obj.object_list:
                        # Get actual rank from user_rank_map (source of truth)
                        app.actual_rank = user_rank_map.get(app.user_id)
                    context['rankings'] = page_obj.object_list
                    context['object_list'] = page_obj.object_list
                    context['page_obj'] = page_obj
                    context['is_paginated'] = page_obj.has_other_pages()
                    context['paginator'] = paginator
            else:
                # For top 5, use unfiltered_list to ensure correct ranking order
                # This ensures ranks are always accurate even when follower counts change
                top5 = unfiltered_list[:5]
                # actual_rank is already set when we built unfiltered_list above
                # Double-check to ensure it's set correctly (should match index)
                for index, app in enumerate(top5, start=1):
                    expected_rank = user_rank_map.get(app.user_id)
                    app.actual_rank = expected_rank if expected_rank is not None else index
                    # Verify it matches (debugging)
                    if app.actual_rank != index:
                        logger.warning(f"Rank mismatch for user {app.user_id}: expected {index}, got {app.actual_rank}")
                context['rankings'] = top5
                context['object_list'] = top5
                context['is_paginated'] = False
            context['total_editors'] = len(unfiltered_list) if search_query else queryset.count()
        
        # Edit of the Week: Weekly competition system
        # Competition runs Monday 00:00 to Friday 23:59
        # Saturday-Sunday shows winners only
        try:
            competition_state = get_competition_state()
            week_start, week_end = get_week_start_end()
        except Exception as e:
            logger.error(f"Error getting competition state: {e}")
            # Fallback: treat as live competition
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            days_since_monday = (now.weekday()) % 7
            week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=4, hours=23, minutes=59, seconds=59)
            competition_state = {
                'state': 'live' if now < week_end else 'winners',
                'week_start': week_start,
                'week_end': week_end,
                'time_remaining': week_end - now if now < week_end else timedelta(0),
                'next_week_start': week_start + timedelta(days=7),
            }
        
        edit_platform = self.request.GET.get('edit_platform', 'youtube')
        if edit_platform not in ['youtube', 'tiktok']:
            edit_platform = 'youtube'
        
        # Filter edits by CURRENT week (full week Mon-Sun for display)
        # Show edits scheduled for the current week (Mon-Sun)
        display_week_start = week_start  # Current week Monday
        display_week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)  # Current week Sunday
        display_week_start_date = display_week_start.date()
        competition_end = competition_state.get('competition_end', week_start + timedelta(days=4, hours=23, minutes=59, seconds=59))
        
        # Show top 3 edits from current week (Mon-Sun) - same logic for both live and results states
        # Display edits from the current week (Mon-Sun)
        week_edits_qs = EditSubmission.objects.filter(
            status='verified',
            channel_type=edit_platform
        ).filter(
            Q(scheduled_week=display_week_start_date) |
            (Q(scheduled_week__isnull=True) & Q(submitted_date__gte=display_week_start) & Q(submitted_date__lte=display_week_end))
        ).order_by('-calculated_points', 'submitted_date')
        
        # Get top 3 from current week
        top_three = list(week_edits_qs[:3])
        # Attach thumbnails via oEmbed/ID extraction for custom cards
        from .utils import fetch_tiktok_oembed, youtube_thumbnail_from_url
        enriched = []
        for edit in top_three:
            if edit.channel_type == 'youtube':
                thumb = youtube_thumbnail_from_url(edit.video_url)
                embed_html = None
            else:
                oembed_data = fetch_tiktok_oembed(edit.video_url)
                thumb = oembed_data.get('thumbnail_url')
                embed_html = oembed_data.get('html')  # Get TikTok's official embed HTML
            
            enriched.append({
                'instance': edit,
                'id': edit.id,
                'video_url': edit.video_url,
                'direct_video_url': getattr(edit, 'direct_video_url', None),  # For TikTok HTML5 video player (deprecated, using embed now)
                'tiktok_embed_html': embed_html,  # TikTok's official embed HTML from oEmbed API
                'channel_type': edit.channel_type,
                'channel_name': edit.channel_name,
                'channel_thumbnail': edit.channel_thumbnail,
                'title': getattr(edit, 'title', ''),
                'upvote_count': edit.upvote_count,
                'calculated_points': float(edit.calculated_points),
                'week_rank': getattr(edit, 'week_rank', None),
                'thumbnail_url': thumb,
            })
        context['top_edits'] = enriched
        context['edit_platform'] = edit_platform  # Current platform for Edit of the Week section
        context['competition_state'] = competition_state
        try:
            context['countdown'] = format_countdown(competition_state.get('time_remaining', timedelta(0))) if competition_state['state'] == 'live' else None
        except:
            context['countdown'] = None
        context['week_start'] = week_start
        context['week_end'] = week_end
        
        # Convert datetime objects to ISO format for JavaScript
        try:
            if competition_state['state'] == 'live':
                # Show countdown to competition end (Friday)
                context['competition_end_iso'] = competition_end.isoformat()
            else:
                # Show countdown to next week start (Monday)
                context['next_week_start_iso'] = competition_state.get('next_week_start', week_start + timedelta(days=7)).isoformat()
        except:
            context['competition_end_iso'] = competition_end.isoformat() if 'competition_end' in locals() else None
        
        # Check if user has already submitted an edit for the next week
        # (submissions are queued for next week, so we check next week's start date)
        user_has_submitted_this_week = False
        if self.request.user.is_authenticated and competition_state['state'] == 'live':
            next_week_start_date = (week_start + timedelta(days=7)).date()
            user_has_submitted_this_week = EditSubmission.objects.filter(
                user=self.request.user,
                scheduled_week=next_week_start_date
            ).exists()
        context['user_has_submitted_this_week'] = user_has_submitted_this_week
        
        # Tournament participants - Get from active tournament
        from .models import Tournament
        active_tournament = Tournament.get_active_tournament()
        
        # Pass tournament to context for conditional rendering
        context['tournament'] = active_tournament
        
        # Phase status
        context['semi_finals_active'] = False
        context['finals_active'] = False
        
        tournament_participants = []
        tournament_finalists = []
        
        if active_tournament and active_tournament.is_active:
            # Get phase status
            context['semi_finals_active'] = active_tournament.semi_finals_active
            context['finals_active'] = active_tournament.finals_active
            
            # Get semi-final participants
            if active_tournament.semi_finals_active:
                participants = active_tournament.get_participants()
                for app in participants:
                    if app:
                        tournament_participants.append({
                            'user': app.user,
                            'app': app,
                            'channel_name': app.channel_name or app.user.username,
                            'username': app.user.username,
                            'profile_picture': app.user.profile_picture.url if app.user.profile_picture else None,
                            'channel_thumbnail': (app.channel_thumbnail or '').strip(),
                            'channel_type': app.channel_type,
                            'editor_title': app.editor_title,  # Use property which handles custom titles
                            'editor_title_rarity': app.editor_title_rarity,  # Include rarity for styling
                        })
                    else:
                        tournament_participants.append(None)
            else:
                # Semi-finals not active, show empty slots
                tournament_participants = [None, None, None, None]
            
            # Get finalists
            if active_tournament.finals_active:
                finalists = active_tournament.get_finalists()
                for app in finalists:
                    if app:
                        tournament_finalists.append({
                            'user': app.user,
                            'app': app,
                            'channel_name': app.channel_name or app.user.username,
                            'username': app.user.username,
                            'profile_picture': app.user.profile_picture.url if app.user.profile_picture else None,
                            'channel_thumbnail': (app.channel_thumbnail or '').strip(),
                            'channel_type': app.channel_type,
                            'editor_title': app.editor_title,  # Use property which handles custom titles
                            'editor_title_rarity': app.editor_title_rarity,  # Include rarity for styling
                        })
                    else:
                        tournament_finalists.append(None)
            else:
                # Finals not active, show empty slots
                tournament_finalists = [None, None]
        else:
            # No active tournament, show empty slots
            tournament_participants = [None, None, None, None]
            tournament_finalists = [None, None]
        
        # Ensure we have exactly 4 participants (pad with None if needed)
        while len(tournament_participants) < 4:
            tournament_participants.append(None)
        
        # Ensure we have exactly 2 finalists (pad with None if needed)
        while len(tournament_finalists) < 2:
            tournament_finalists.append(None)
        
        context['tournament_participants'] = tournament_participants[:4]
        context['tournament_finalists'] = tournament_finalists[:2]
        
        return context

    def _build_mix_entries(self):
        # Get the unfiltered queryset to calculate actual ranks
        search_query = getattr(self, 'search_query', '').strip()
        
        # Build unfiltered entries first to get actual ranks
        unfiltered_queryset = EditorApplication.objects.filter(
            status='accepted',
            removal_requested=False
        ).select_related('user').order_by('-follower_count', 'applied_date')
        
        # Apply editing area filter if present (but not search filter yet)
        editing_area = getattr(self, 'selected_area', '')
        if editing_area:
            unfiltered_queryset = unfiltered_queryset.filter(
                Q(editing_area=editing_area) | Q(editing_area='all')
            )
        
        applications = list(unfiltered_queryset)
        grouped = defaultdict(list)

        # Group applications by user_id to combine YouTube and TikTok channels
        for application in applications:
            grouped[application.user_id].append(application)

        # Build all entries first with actual ranks
        all_entries = []
        for apps in grouped.values():
            apps.sort(key=lambda app: app.channel_type)
            youtube_app = next((app for app in apps if app.channel_type == 'youtube'), None)
            tiktok_app = next((app for app in apps if app.channel_type == 'tiktok'), None)
            primary_app = youtube_app or tiktok_app or max(apps, key=lambda app: app.follower_count or 0)
            total_followers = sum(app.follower_count or 0 for app in apps)
            seen_areas = set()
            area_badges = []
            for app in apps:
                key = (app.editing_area, app.editing_area_other)
                if key in seen_areas:
                    continue
                seen_areas.add(key)
                area_badges.append({
                    'key': app.editing_area,
                    'label': app.get_editing_area_display(),
                    'extra': app.editing_area_other if app.editing_area == 'others' else '',
                })
            # Deduplicate editing tools - only show unique tools
            seen_tools = set()
            unique_tools = []
            for app in apps:
                if app.editing_tool not in seen_tools:
                    seen_tools.add(app.editing_tool)
                    unique_tools.append(app)
            display_user_name = apps[0].user.get_full_name() or apps[0].user.username
            # Get thumbnail - prefer primary app, but fallback to other platform if primary has no thumbnail
            from .utils import get_fallback_thumbnail
            display_thumbnail = ''
            if primary_app:
                primary_thumb = (primary_app.channel_thumbnail or '').strip()
                youtube_thumb = (youtube_app.channel_thumbnail or '').strip() if youtube_app else ''
                tiktok_thumb = (tiktok_app.channel_thumbnail or '').strip() if tiktok_app else ''
                
                # Use fallback helper to get the best available thumbnail
                if youtube_app and tiktok_app:
                    # User has both platforms - prefer primary, then other platform
                    other_app_thumb = tiktok_thumb if primary_app == youtube_app else youtube_thumb
                    display_thumbnail = get_fallback_thumbnail(primary_thumb, other_app_thumb)
                elif youtube_app:
                    display_thumbnail = get_fallback_thumbnail(primary_thumb, youtube_thumb)
                elif tiktok_app:
                    display_thumbnail = get_fallback_thumbnail(primary_thumb, tiktok_thumb)
                else:
                    display_thumbnail = primary_thumb if primary_thumb else ''
            all_entries.append({
                'user': apps[0].user,
                'apps': apps,
                'unique_tools': unique_tools,  # Deduplicated list of apps with unique editing tools
                'youtube': youtube_app,
                'tiktok': tiktok_app,
                'primary': primary_app,
                'display_thumbnail': display_thumbnail,
                'display_platform': primary_app.channel_type if primary_app else None,
                'display_user_name': display_user_name,
                'total_followers': total_followers,
                'areas': area_badges,
                'followers': {
                    'youtube': youtube_app.follower_count if youtube_app else 0,
                    'tiktok': tiktok_app.follower_count if tiktok_app else 0,
                }
            })

        # Sort and assign actual ranks
        all_entries.sort(
            key=lambda entry: (
                -(entry['total_followers'] or 0),
                entry['primary'].applied_date if entry['primary'] else None
            )
        )

        # Create a mapping of user_id to actual rank
        user_rank_map = {}
        for index, entry in enumerate(all_entries, start=1):
            entry['rank'] = index
            user_rank_map[entry['user'].id] = index

        # Now filter by search query if provided, but preserve actual ranks
        if search_query:
            search_lower = search_query.lower()
            filtered_entries = []
            for entry in all_entries:
                # Check if any app for this user matches the search
                matches = False
                for app in entry['apps']:
                    if (search_lower in (app.channel_name or '').lower() or
                        search_lower in (app.user.username or '').lower() or
                        search_lower in (app.user.email or '').lower()):
                        matches = True
                        break
                if matches:
                    # Preserve the actual rank from the unfiltered list
                    filtered_entries.append(entry)
            return filtered_entries

        return all_entries


@login_required
def apply_view(request):
    """View for submitting editor applications"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can apply to the EditingHub.")
        return redirect('home')
    
    def build_form(prefix, channel_type, data=None, files=None):
        form = EditorApplicationForm(data=data, files=files, prefix=prefix)
        form.initial.setdefault('channel_type', channel_type)
        form.fields['channel_type'].initial = channel_type
        form.fields['channel_type'].widget = forms.HiddenInput()
        form.fields['channel_type'].required = True
        form.fields['data_consent'].widget = forms.HiddenInput()
        form.fields['data_consent'].required = False
        return form

    def render_apply_form(youtube_form, tiktok_form, apply_youtube=True, apply_tiktok=False, data_consent_checked=False):
        user_applications = EditorApplication.objects.filter(user=request.user).order_by('-applied_date')
        grouped_existing = {
            'youtube': [app for app in user_applications if app.channel_type == 'youtube'],
            'tiktok': [app for app in user_applications if app.channel_type == 'tiktok'],
        }
        
        # Check if user has active applications (pending or accepted) for each platform
        youtube_active = EditorApplication.objects.filter(
            user=request.user,
            channel_type='youtube',
            status__in=['pending', 'accepted']
        ).exclude(removal_requested=True).exists()
        
        tiktok_active = EditorApplication.objects.filter(
            user=request.user,
            channel_type='tiktok',
            status__in=['pending', 'accepted']
        ).exclude(removal_requested=True).exists()
        
        return render(request, 'edithub/apply.html', {
            'youtube_form': youtube_form,
            'tiktok_form': tiktok_form,
            'apply_youtube': apply_youtube,
            'apply_tiktok': apply_tiktok,
            'data_consent_checked': data_consent_checked,
            'existing_applications': user_applications,
            'existing_applications_grouped': grouped_existing,
            'youtube_already_applied': youtube_active,
            'tiktok_already_applied': tiktok_active,
        })

    if request.method == 'POST':
        selected_platform = request.POST.get('platform')
        data_consent = request.POST.get('data_consent') == 'on'

        if not selected_platform or selected_platform not in ['youtube', 'tiktok']:
            messages.error(request, "Please select a platform to apply for.")
            youtube_form = build_form('youtube', 'youtube')
            tiktok_form = build_form('tiktok', 'tiktok')
            apply_youtube = selected_platform == 'youtube' if selected_platform else True
            apply_tiktok = selected_platform == 'tiktok' if selected_platform else False
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        if not data_consent:
            messages.error(request, "You must consent to data usage to proceed.")
            youtube_form = build_form('youtube', 'youtube')
            tiktok_form = build_form('tiktok', 'tiktok')
            apply_youtube = selected_platform == 'youtube'
            apply_tiktok = selected_platform == 'tiktok'
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        # Early file size validation BEFORE form processing
        from core.validators import MAX_CHANNEL_SCREENSHOT_SIZE_MB
        prefix = selected_platform
        screenshot_key = f'{prefix}-channel_screenshot'
        
        if screenshot_key in request.FILES:
            uploaded_file = request.FILES[screenshot_key]
            max_size_bytes = MAX_CHANNEL_SCREENSHOT_SIZE_MB * 1024 * 1024
            if uploaded_file.size > max_size_bytes:
                file_size_mb = uploaded_file.size / (1024 * 1024)
                messages.error(
                    request, 
                    f"File too large. Maximum size is {MAX_CHANNEL_SCREENSHOT_SIZE_MB} MB. "
                    f"Your file is {file_size_mb:.2f} MB. Please compress or resize your image."
                )
                youtube_form = build_form('youtube', 'youtube')
                tiktok_form = build_form('tiktok', 'tiktok')
                apply_youtube = selected_platform == 'youtube'
                apply_tiktok = selected_platform == 'tiktok'
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        # Prepare form for selected platform only
        post_data = request.POST.copy()
        post_data[f'{prefix}-channel_type'] = selected_platform
        post_data[f'{prefix}-data_consent'] = 'on'
        
        if selected_platform == 'youtube':
            youtube_form = build_form('youtube', 'youtube', data=post_data, files=request.FILES)
            tiktok_form = build_form('tiktok', 'tiktok')
            apply_youtube = True
            apply_tiktok = False
        else:
            youtube_form = build_form('youtube', 'youtube')
            tiktok_form = build_form('tiktok', 'tiktok', data=post_data, files=request.FILES)
            apply_youtube = False
            apply_tiktok = True

        forms_to_process = []
        if selected_platform == 'youtube':
            if youtube_form.is_valid():
                forms_to_process.append(('youtube', youtube_form))
            else:
                logger.warning("YouTube form validation failed: %s", youtube_form.errors)
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)
        else:
            if tiktok_form.is_valid():
                forms_to_process.append(('tiktok', tiktok_form))
            else:
                logger.warning("TikTok form validation failed: %s", tiktok_form.errors)
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        # Ensure user does not already have an active application for selected platform
        for platform, form in forms_to_process:
            existing_active = EditorApplication.objects.filter(
                user=request.user,
                channel_type=platform,
                status__in=['pending', 'accepted']
            ).exclude(removal_requested=True)
            if existing_active.exists():
                messages.error(
                    request,
                    f"You already have a {platform.title()} application in progress. Please wait for it to be reviewed or request removal before applying again."
                )
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

            channel_link = form.cleaned_data['channel_link'].strip()
            # Only check for active applications (pending or accepted, not removal_requested)
            # This allows re-application if the previous application was deleted/rejected/removed
            duplicate_link = EditorApplication.objects.filter(
                user=request.user,
                channel_link=channel_link,
                status__in=['pending', 'accepted']
            ).exclude(removal_requested=True)
            if duplicate_link.exists():
                messages.error(request, "You have already submitted this channel link with an active application.")
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        created_applications = []

        try:
            from django.db import IntegrityError
            for platform, form in forms_to_process:
                channel_link = form.cleaned_data['channel_link'].strip()

                if platform == 'youtube':
                    channel_data = fetch_youtube_channel_data(channel_link)
                else:
                    channel_data = fetch_tiktok_channel_data(channel_link)

                # For TikTok, be more lenient - allow application if we at least got the username
                # The error might be a timeout but we might still have some data
                if channel_data.get('error'):
                    if platform == 'tiktok' and channel_data.get('channel_name'):
                        # We have at least the username, allow it but log the error
                        logger.warning(f"TikTok fetch had error but got channel_name: {channel_data['error']}")
                        # Clear the error so application can proceed
                        channel_data['error'] = None
                    else:
                        raise ValueError(f"Failed to fetch {platform.title()} data: {channel_data['error']}")

                application = EditorApplication(
                    user=request.user,
                    channel_link=channel_link,
                    channel_type=platform,
                    editing_area=form.cleaned_data['editing_area'],
                    editing_area_other=form.cleaned_data.get('editing_area_other', ''),
                    editing_tool=form.cleaned_data['editing_tool'],
                    channel_name=channel_data.get('channel_name', ''),
                    follower_count=channel_data.get('subscriber_count') or channel_data.get('follower_count', 0),
                    channel_thumbnail=channel_data.get('thumbnail', ''),
                    channel_screenshot=form.cleaned_data['channel_screenshot'],
                    channel_verified=False,
                    data_consent=True,
                    status='pending'
                )
                application.save()
                created_applications.append(application)
                logger.info(
                    "Created %s application %s for user %s",
                    platform,
                    application.pk,
                    request.user.username
                )

        except IntegrityError as error:
            # Handle unique_together constraint violation
            # This can happen if a deleted application still exists in the database
            logger.warning("Integrity error while creating application: %s", error)
            for app in created_applications:
                app.delete()
            # Check if it's a duplicate channel_link issue
            if 'channel_link' in str(error) or 'unique' in str(error).lower():
                messages.error(
                    request, 
                    "An application with this channel link already exists. "
                    "If your previous application was deleted, please contact support or try again in a few moments."
                )
            else:
                messages.error(request, f"Database error: {error}")
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)
        except ValueError as error:
            logger.warning("Application processing error: %s", error)
            for app in created_applications:
                app.delete()
            messages.error(request, str(error))
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)
        except Exception as error:
            logger.error("Unexpected error while processing applications", exc_info=True)
            for app in created_applications:
                app.delete()
            messages.error(request, f"An unexpected error occurred: {error}")
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        pending_ids = [app.pk for app in created_applications]
        request.session['pending_application_ids'] = pending_ids
        if pending_ids:
            request.session['pending_application_id'] = pending_ids[0]
        request.session.save()

        return redirect('edithub:confirm_application')

    # GET request - initialise forms
    youtube_form = build_form('youtube', 'youtube')
    tiktok_form = build_form('tiktok', 'tiktok')
    
    # Check if platform is specified in query params
    edit_platform = request.GET.get('edit_platform', '').lower()
    if edit_platform == 'youtube':
        apply_youtube = True
        apply_tiktok = False
    elif edit_platform == 'tiktok':
        apply_youtube = False
        apply_tiktok = True
    else:
        apply_youtube = True
        apply_tiktok = False

    return render_apply_form(youtube_form, tiktok_form, apply_youtube=apply_youtube, apply_tiktok=apply_tiktok, data_consent_checked=False)


@require_http_methods(["GET"])
def get_user_stats_ajax(request):
    """AJAX endpoint to get user statistics for modal display"""
    try:
        user_id = request.GET.get('user_id')
        if not user_id:
            return JsonResponse({'error': 'User ID is required'}, status=400)
        
        try:
            edit_user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Get all accepted channel applications for this user
        accepted_apps = EditorApplication.objects.filter(
            user=edit_user,
            status='accepted'
        )
        
        if not accepted_apps.exists():
            return JsonResponse({'error': 'No channel found for this user'}, status=404)
        
        # Get primary channel (highest follower count)
        primary_app = accepted_apps.order_by('-follower_count').first()
        
        # Check if user has both YouTube and TikTok
        youtube_app = accepted_apps.filter(channel_type='youtube').first()
        tiktok_app = accepted_apps.filter(channel_type='tiktok').first()
        
        has_both = youtube_app is not None and tiktok_app is not None
        
        # Calculate user statistics
        total_edits = EditSubmission.objects.filter(
            user=edit_user,
            status='verified'
        ).count()
        
        # Count Edit of the Week wins (top 3 finishes)
        edit_of_week_wins = EditSubmission.objects.filter(
            user=edit_user,
            status='verified',
            week_rank__in=[1, 2, 3]
        ).count()
        
        # Count Edit of the Month wins
        from django.utils import timezone
        from datetime import datetime
        from calendar import monthrange
        
        edit_of_month_wins = 0
        user_edits = EditSubmission.objects.filter(
            user=edit_user,
            status='verified'
        ).order_by('scheduled_week', 'submitted_date')
        
        months_checked = set()
        for edit in user_edits:
            reference_date = edit.scheduled_week or edit.submitted_date.date()
            year_month = (reference_date.year, reference_date.month)
            if year_month in months_checked:
                continue
            months_checked.add(year_month)
            
            first_day = datetime(year_month[0], year_month[1], 1, tzinfo=timezone.utc)
            last_day_num = monthrange(year_month[0], year_month[1])[1]
            last_day = datetime(year_month[0], year_month[1], last_day_num, 23, 59, 59, tzinfo=timezone.utc)
            
            top_edit = EditSubmission.objects.filter(
                status='verified',
                scheduled_week__gte=first_day.date(),
                scheduled_week__lte=last_day.date()
            ).order_by('-calculated_points', 'submitted_date').first()
            
            if top_edit and top_edit.user == edit_user:
                edit_of_month_wins += 1
        
        # Get user's best rank (only from weeks that have started)
        from datetime import date
        today = date.today()
        best_rank = EditSubmission.objects.filter(
            user=edit_user,
            status='verified',
            scheduled_week__lte=today  # Only count points from weeks that have started
        ).order_by('-calculated_points').first()
        best_points = float(best_rank.calculated_points) if best_rank else 0.0
        
        # Get editor title (using property which handles custom titles)
        editor_title = primary_app.editor_title
        editor_title_rarity = primary_app.editor_title_rarity
        
        response_data = {
            'success': True,
            'username': primary_app.channel_name or edit_user.username,
            'profile_picture': (primary_app.channel_thumbnail or '').strip(),
            'channel_type': primary_app.channel_type,
            'channel_link': primary_app.channel_link,
            'editor_title': editor_title,
            'editor_title_rarity': editor_title_rarity,
            'total_edits': total_edits,
            'edit_of_week_wins': edit_of_week_wins,
            'edit_of_month_wins': edit_of_month_wins,
            'best_points': best_points,
        }
        
        # Add both channel links if user has both platforms
        if has_both:
            response_data['has_both_platforms'] = True
            response_data['youtube_link'] = youtube_app.channel_link if youtube_app else None
            response_data['tiktok_link'] = tiktok_app.channel_link if tiktok_app else None
        else:
            response_data['has_both_platforms'] = False
        
        return JsonResponse(response_data)
    
    except Exception as e:
        logger.error(f"Error fetching user stats: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_available_titles(request):
    """Get available editor titles for the current user, grouped by category"""
    from .models import EditorTitle, EditorApplication
    from .utils import is_title_unlocked_for_user
    
    # Get user's primary application
    primary_app = EditorApplication.objects.filter(
        user=request.user,
        status='accepted'
    ).order_by('-follower_count').first()
    
    if not primary_app:
        return JsonResponse({
            'success': False,
            'error': 'No accepted application found. Please apply to join the rankings first.'
        }, status=404)
    
    # Get all active titles grouped by category
    try:
        titles = EditorTitle.objects.filter(is_active=True).order_by('category', 'rarity', 'cost_coins', 'name')
    except Exception as e:
        # If category field doesn't exist yet (migration not run), fall back to old query
        logger.warning(f"Error querying titles with category: {e}")
        titles = EditorTitle.objects.filter(is_active=True).order_by('rarity', 'cost_coins', 'name')
    
    # Group titles by category
    titles_by_category = {
        'reel': [],
        'comment': [],
        'general': []
    }
    
    for title in titles:
        # Get category, defaulting to 'general' if field doesn't exist
        title_category = getattr(title, 'category', 'general')
        
        # Check if title is unlocked
        is_unlocked = is_title_unlocked_for_user(request.user, title)
        
        # Get achievement progress if applicable
        achievement_progress = None
        if not is_unlocked and getattr(title, 'achievement_type', None) and getattr(title, 'unlock_method', 'coins') in ['achievement', 'both']:
            from .utils import get_user_achievement_progress
            achievement_progress = get_user_achievement_progress(request.user, title)
        
        title_data = {
            'id': title.id,
            'name': title.name,
            'rarity': title.rarity,
            'category': title_category,
            'description': title.description or '',
            'cost_coins': title.cost_coins,
            'is_selected': primary_app.selected_title_id == title.id if primary_app.selected_title else False,
            'is_unlocked': is_unlocked,
            'unlock_requirement': title.unlock_requirement or '',
            'unlock_method': getattr(title, 'unlock_method', 'coins'),
            'achievement_type': getattr(title, 'achievement_type', None),
            'achievement_threshold': getattr(title, 'achievement_threshold', 0),
            'achievement_progress': achievement_progress,  # Current progress towards achievement
        }
        
        # For comment titles, only show YouTube/TikTok Editor based on user's channel type
        if title_category == 'comment':
            if title.name.lower() == f"{primary_app.channel_type} editor":
                titles_by_category['comment'].append(title_data)
        else:
            # Ensure category exists in our dict, default to 'general' if not
            category_key = title_category if title_category in titles_by_category else 'general'
            titles_by_category[category_key].append(title_data)
    
    # Get current title info
    current_title = None
    if primary_app.selected_title:
        current_title = {
            'id': primary_app.selected_title.id,
            'name': primary_app.selected_title.name,
            'rarity': primary_app.selected_title.rarity,
            'category': getattr(primary_app.selected_title, 'category', 'general'),
        }
    else:
        # Default title based on channel type
        current_title = {
            'id': None,
            'name': f"{primary_app.channel_type.title()} Editor",
            'rarity': 'ordinary',
            'category': 'comment',
        }
    
    return JsonResponse({
        'success': True,
        'titles_by_category': titles_by_category,
        'current_title': current_title,
        'current_title_id': primary_app.selected_title_id if primary_app.selected_title else None,
    })


@login_required
def customize_profile(request):
    """Profile customization page with title selection"""
    from .models import EditorApplication
    
    # Get user's primary application
    primary_app = EditorApplication.objects.filter(
        user=request.user,
        status='accepted'
    ).order_by('-follower_count').first()
    
    if not primary_app:
        messages.warning(request, 'You need to have an accepted application to customize your profile.')
        return redirect('edithub:apply')
    
    # Get all accepted applications for channel switching
    all_apps = EditorApplication.objects.filter(
        user=request.user,
        status='accepted',
        removal_requested=False
    ).order_by('-follower_count')
    
    # Get available channels for profile switching
    available_channels = request.user.get_available_channels()
    
    # Get current title info
    current_title = None
    if primary_app.selected_title:
        current_title = {
            'id': primary_app.selected_title.id,
            'name': primary_app.selected_title.name,
            'rarity': primary_app.selected_title.rarity,
            'category': getattr(primary_app.selected_title, 'category', 'general'),
        }
    else:
        # Default title based on channel type
        current_title = {
            'id': None,
            'name': f"{primary_app.channel_type.title()} Editor",
            'rarity': 'ordinary',
            'category': 'comment',
        }
    
    # Get display name and picture based on current mode
    display_name = request.user.get_display_name()
    display_picture = request.user.get_display_picture()
    
    context = {
        'primary_app': primary_app,
        'current_title': current_title,
        'user': request.user,
        'display_name': display_name,
        'display_picture': display_picture,
        'available_channels': available_channels,
        'all_apps': all_apps,
    }
    
    return render(request, 'edithub/customize_profile.html', context)


@login_required
@require_http_methods(["POST"])
def switch_profile_mode(request):
    """Switch between account and channel profile display"""
    import json
    from .models import EditorApplication
    
    try:
        data = json.loads(request.body)
        mode = data.get('mode', 'account')
        channel_source = data.get('channel_source', None)
        
        if mode not in ['account', 'channel']:
            return JsonResponse({'success': False, 'error': 'Invalid mode'}, status=400)
        
        user = request.user
        
        # Validate channel source if switching to channel mode
        if mode == 'channel':
            # Check if user has any accepted applications
            has_apps = EditorApplication.objects.filter(
                user=user,
                status='accepted',
                removal_requested=False
            ).exists()
            
            if not has_apps:
                return JsonResponse({
                    'success': False, 
                    'error': 'You need to have an accepted application to use channel profile mode.'
                }, status=400)
            
            # If channel_source is specified, validate it
            if channel_source:
                valid_channel = EditorApplication.objects.filter(
                    user=user,
                    channel_type=channel_source,
                    status='accepted',
                    removal_requested=False
                ).exists()
                
                if not valid_channel:
                    return JsonResponse({
                        'success': False,
                        'error': f'You do not have an accepted {channel_source} application.'
                    }, status=400)
                
                user.profile_channel_source = channel_source
            else:
                # If no channel_source specified, clear it (will use primary)
                user.profile_channel_source = None
        
        # Update profile display mode
        user.profile_display_mode = mode
        user.save()
        
        # Get updated display info
        display_name = user.get_display_name()
        display_picture = user.get_display_picture()
        
        # Check if user has multiple channels
        channel_count = EditorApplication.objects.filter(
            user=user,
            status='accepted',
            removal_requested=False
        ).count()
        
        return JsonResponse({
            'success': True,
            'display_name': display_name,
            'display_picture': display_picture,
            'has_multiple_channels': channel_count > 1,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error switching profile mode: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred'}, status=500)


@login_required
@require_http_methods(["POST"])
def select_editor_title(request):
    """Select an editor title for the user"""
    from .models import EditorTitle, EditorApplication, UserTitleUnlock
    from .utils import is_title_unlocked_for_user
    import json
    
    try:
        data = json.loads(request.body)
        title_id = data.get('title_id')
        
        if not title_id:
            return JsonResponse({'error': 'Title ID is required'}, status=400)
        
        # Get user's primary application
        primary_app = EditorApplication.objects.filter(
            user=request.user,
            status='accepted'
        ).order_by('-follower_count').first()
        
        if not primary_app:
            return JsonResponse({'error': 'No accepted application found'}, status=404)
        
        # Get the title
        try:
            title = EditorTitle.objects.get(id=title_id, is_active=True)
        except EditorTitle.DoesNotExist:
            return JsonResponse({'error': 'Title not found'}, status=404)
        
        # Update the selected title (only for reel and general categories)
        # Comment titles are automatically set based on channel type
        if title.category == 'comment':
            return JsonResponse({
                'error': 'Comment titles cannot be manually selected. They are automatically set based on your channel type.'
            }, status=400)
        
        # Check if title is unlocked
        is_unlocked = is_title_unlocked_for_user(request.user, title)
        
        if not is_unlocked:
            # Provide helpful error message
            if title.unlock_method == 'achievement':
                error_msg = f"This title is locked. {title.unlock_requirement or 'Complete the achievement requirements to unlock.'}"
            elif title.unlock_method == 'coins':
                error_msg = f"This title costs {title.cost_coins} coins. You don't have enough coins to unlock it."
            elif title.unlock_method == 'both':
                error_msg = f"This title requires either {title.cost_coins} coins or completing: {title.unlock_requirement or 'the achievement requirements'}."
            else:
                error_msg = f"This title is locked. {title.unlock_requirement or 'Complete the requirements to unlock.'}"
            
            return JsonResponse({
                'error': error_msg,
                'is_locked': True
            }, status=403)
        
        # Update the selected title
        primary_app.selected_title = title
        primary_app.save(update_fields=['selected_title'])
        
        return JsonResponse({
            'success': True,
            'title_name': title.name,
            'title_rarity': title.rarity,
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error selecting title: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def verify_channel_ajax(request):
    """AJAX endpoint to verify and fetch channel data"""
    if request.user.role != 'user':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        data = json.loads(request.body)
        channel_url = data.get('channel_url', '').strip()
        
        if not channel_url:
            return JsonResponse({'error': 'Channel URL is required'}, status=400)
        
        # Validate URL
        is_valid, channel_type, error_message = validate_channel_url(channel_url)
        if not is_valid:
            return JsonResponse({'error': error_message or 'Invalid URL'}, status=400)
        
        # Fetch channel data
        if channel_type == 'youtube':
            channel_data = fetch_youtube_channel_data(channel_url)
        else:  # tiktok
            channel_data = fetch_tiktok_channel_data(channel_url)
        
        if channel_data.get('error'):
            return JsonResponse({
                'error': channel_data['error'],
                'channel_type': channel_type
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'channel_type': channel_type,
            'channel_name': channel_data.get('channel_name', ''),
            'follower_count': channel_data.get('subscriber_count') or channel_data.get('follower_count', 0),
            'thumbnail': channel_data.get('thumbnail', ''),
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def confirm_application(request):
    """Confirmation page after form submission"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can apply to the EditingHub.")
        return redirect('home')
    
    # Get applications from session
    application_ids = request.session.get('pending_application_ids')
    single_id = request.session.get('pending_application_id')

    if application_ids and isinstance(application_ids, int):
        application_ids = [application_ids]
    if not application_ids and single_id:
        application_ids = [single_id]

    if not application_ids:
        messages.error(request, "No application data found. Please start over.")
        return redirect('edithub:apply')

    applications_qs = EditorApplication.objects.filter(pk__in=application_ids, user=request.user)
    applications_map = {app.pk: app for app in applications_qs}
    applications = [applications_map[app_id] for app_id in application_ids if app_id in applications_map]

    if not applications:
        messages.error(request, "Application not found. Please start over.")
        request.session.pop('pending_application_ids', None)
        request.session.pop('pending_application_id', None)
        return redirect('edithub:apply')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'confirm':
            for application in applications:
                application.channel_verified = True
                application.save()

            request.session.pop('pending_application_ids', None)
            request.session.pop('pending_application_id', None)

            if len(applications) == 1:
                messages.success(request, "Application submitted successfully! It will be reviewed by an admin.")
                return redirect('edithub:application_detail', pk=applications[0].pk)

            messages.success(request, "Applications submitted successfully! They will be reviewed by an admin.")
            return redirect('edithub:application_detail', pk=applications[0].pk)

        # Cancel action
        for application in applications:
            application.delete()
        request.session.pop('pending_application_ids', None)
        request.session.pop('pending_application_id', None)
        messages.info(request, "Application cancelled. You can modify and resubmit.")
        return redirect('edithub:apply')

    application_summaries = []
    for application in applications:
        application_summaries.append({
            'instance': application,
            'channel_link': application.channel_link,
            'channel_type': application.channel_type,
            'editing_area': application.editing_area,
            'editing_area_other': application.editing_area_other,
            'editing_tool': application.editing_tool,
            'channel_name': application.channel_name,
            'follower_count': application.follower_count,
            'channel_thumbnail': application.channel_thumbnail,
        })

    context = {
        'applications': application_summaries,
    }
    return render(request, 'edithub/confirm_application.html', context)


@login_required
def application_detail(request, pk):
    """View application details"""
    application = get_object_or_404(EditorApplication, pk=pk)
    
    # Users can only view their own applications, admins can view all
    if request.user != application.user and request.user.role != 'admin':
        messages.error(request, "You don't have permission to view this application.")
        return redirect('edithub:ranking_table')
    
    context = {
        'application': application,
        'can_edit': (request.user == application.user and application.status == 'pending'),
        'can_remove': (request.user == application.user and application.status == 'accepted'),
    }
    
    return render(request, 'edithub/application_detail.html', context)


@login_required
def request_removal(request, pk):
    """Allow users to request removal of their accepted application"""
    application = get_object_or_404(EditorApplication, pk=pk, user=request.user)
    
    if application.status != 'accepted':
        messages.error(request, "You can only request removal of accepted applications.")
        return redirect('edithub:application_detail', pk=pk)
    
    if request.method == 'POST':
        application.removal_requested = True
        from django.utils import timezone
        application.removal_requested_date = timezone.now()
        application.save()
        
        # Update rankings
        EditorApplication.update_rank_positions()
        
        messages.success(request, "Removal request submitted. Your profile will be removed from the ranking table.")
        return redirect('edithub:application_detail', pk=pk)
    
    return render(request, 'edithub/request_removal.html', {'application': application})


@login_required
def admin_applications(request):
    """Admin view to see all applications and manage them"""
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin account required.")
        return redirect('home')
    
    # Filter applications
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '')
    
    applications_qs = EditorApplication.objects.all().select_related('user').order_by('-applied_date')

    if status_filter != 'all':
        applications_qs = applications_qs.filter(status=status_filter)

    if search_query:
        applications_qs = applications_qs.filter(
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(channel_name__icontains=search_query) |
            Q(channel_link__icontains=search_query)
        )

    grouped = {}
    for application in applications_qs:
        bucket = grouped.setdefault(application.user_id, {
            'user': application.user,
            'youtube': [],
            'tiktok': [],
            'latest_applied': application.applied_date,
        })
        bucket[application.channel_type].append(application)
        if application.applied_date > bucket['latest_applied']:
            bucket['latest_applied'] = application.applied_date

    application_groups = []
    for bucket in grouped.values():
        bucket['youtube'].sort(key=lambda app: app.applied_date, reverse=True)
        bucket['tiktok'].sort(key=lambda app: app.applied_date, reverse=True)
        pending_count = sum(1 for app in bucket['youtube'] + bucket['tiktok'] if app.status == 'pending')
        application_groups.append({
            'user': bucket['user'],
            'youtube': bucket['youtube'],
            'tiktok': bucket['tiktok'],
            'latest_applied': bucket['latest_applied'],
            'pending_count': pending_count,
        })

    application_groups.sort(key=lambda item: item['latest_applied'], reverse=True)

    paginator = Paginator(application_groups, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'application_groups_page': page_obj,
        'application_groups': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'status_filter': status_filter,
        'search_query': search_query,
        'total_pending': EditorApplication.objects.filter(status='pending').count(),
        'total_accepted': EditorApplication.objects.filter(status='accepted', removal_requested=False).count(),
        'total_rejected': EditorApplication.objects.filter(status='rejected').count(),
    }
    
    return render(request, 'edithub/admin_applications.html', context)


@login_required
@require_http_methods(["POST"])
def admin_update_status(request, pk):
    """Admin endpoint to update application status"""
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    application = get_object_or_404(EditorApplication, pk=pk)
    old_status = application.status
    new_status = request.POST.get('status')
    
    if new_status not in dict(EditorApplication.STATUS_CHOICES):
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    application.status = new_status
    if new_status in ['accepted', 'rejected']:
        from django.utils import timezone
        application.reviewed_date = timezone.now()
        application.reviewed_by = request.user
    
    application.save()
    
    # Update rankings if status changed to accepted
    if new_status == 'accepted':
        EditorApplication.update_rank_positions()
    
    # Send notification to user about status change
    if old_status != new_status and new_status in ['accepted', 'rejected']:
        from notifications.manager import notification_manager
        
        if new_status == 'accepted':
            notification_manager.create_notification(
                user=application.user,
                title="Application Approved! 🎉",
                message=f"Great news! Your {application.channel_type.title()} channel application has been approved. You can now participate in the EditingHub rankings and submit edits for Edit of the Week!",
                notification_type='application_approved',
                related_object=application
            )
        elif new_status == 'rejected':
            notification_manager.create_notification(
                user=application.user,
                title="Application Status Update",
                message=f"Your {application.channel_type.title()} channel application has been reviewed. Unfortunately, it was not approved at this time. Please review the requirements and feel free to apply again in the future.",
                notification_type='application_disapproved',
                related_object=application
            )
    
    messages.success(request, f"Application status updated to {application.get_status_display()}")
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': new_status})
    
    return redirect('edithub:admin_applications')


# Edit of the Week Views

def submit_edit(request):
    """View for submitting edits for Edit of the Week"""
    if not request.user.is_authenticated:
        messages.info(request, "Please login to submit your edit for Edit of the Week.")
        from django.urls import reverse
        login_url = reverse('login') + '?next=' + reverse('edithub:submit_edit')
        return redirect(login_url)
    
    if request.user.role != 'user':
        messages.error(request, "Only regular users can submit edits.")
        return redirect('edithub:ranking_table')
    
    youtube_app = EditorApplication.objects.filter(
        user=request.user,
        channel_type='youtube',
        status='accepted',
        removal_requested=False
    ).first()
    tiktok_app = EditorApplication.objects.filter(
        user=request.user,
        channel_type='tiktok',
        status='accepted',
        removal_requested=False
    ).first()
    
    if not youtube_app and not tiktok_app:
        messages.error(request, "You must have an approved channel application before submitting edits. Please apply first.")
        return redirect('edithub:apply')
    
    from .utils import get_week_start_end
    from django.utils import timezone as django_timezone
    from datetime import timezone as dt_timezone
    
    week_start_dt, week_end_dt = get_week_start_end()
    current_week_start = week_start_dt.date()
    next_week_start = (week_start_dt + timedelta(days=7)).date()
    next_week_end = next_week_start + timedelta(days=4)
    next_week_label = f"{next_week_start.strftime('%b %d')} – {next_week_end.strftime('%b %d')}"
    
    # Get existing submissions for next week (only verified ones)
    # Check for pending submissions first - redirect to preview if found
    pending_youtube = EditSubmission.objects.filter(
        user=request.user,
        channel_type='youtube',
        scheduled_week=next_week_start,
        status='pending'
    ).first()
    pending_tiktok = EditSubmission.objects.filter(
        user=request.user,
        channel_type='tiktok',
        scheduled_week=next_week_start,
        status='pending'
    ).first()
    
    # If there's a pending submission, redirect to preview
    if pending_youtube or pending_tiktok:
        pending_submission = pending_youtube or pending_tiktok
        return redirect('edithub:preview_edit_submission', pk=pending_submission.pk)
    
    # Get verified submissions for display
    youtube_future_submission = None
    tiktok_future_submission = None
    
    if youtube_app:
        youtube_future_submission = EditSubmission.objects.filter(
            user=request.user,
            channel_type='youtube',
            scheduled_week=next_week_start,
            status='verified'
        ).first()
    if tiktok_app:
        tiktok_future_submission = EditSubmission.objects.filter(
            user=request.user,
            channel_type='tiktok',
            scheduled_week=next_week_start,
            status='verified'
        ).first()
    
    # Check if we're before the deadline (before Monday 00:00 of next week)
    now = datetime.now(dt_timezone.utc)
    deadline = datetime.combine(next_week_start, datetime.min.time()).replace(tzinfo=dt_timezone.utc)
    can_edit_delete = now < deadline
    
    youtube_form = None
    tiktok_form = None
    
    if request.method == 'POST':
        platform = request.POST.get('platform', '').lower()
        approved_app = None
        
        if platform == 'youtube' and youtube_app:
            approved_app = youtube_app
        elif platform == 'tiktok' and tiktok_app:
            approved_app = tiktok_app
        else:
            messages.error(request, "Invalid platform or you don't have an approved application for this platform.")
            return redirect('edithub:submit_edit')
        
        # Check if submission exists and if we can still edit it
        existing_submission = youtube_future_submission if platform == 'youtube' else tiktok_future_submission
        if existing_submission:
            if not can_edit_delete:
                messages.warning(request, f"You have already submitted a {approved_app.get_channel_type_display()} edit for the week of {next_week_label}. The deadline has passed, so you cannot modify it.")
                return redirect('edithub:submit_edit')
            # If we can edit, redirect to edit view instead
            return redirect('edithub:edit_submission', pk=existing_submission.pk)
        
        form = EditSubmissionForm(data=request.POST, files=request.FILES, approved_application=approved_app)
        
        if form.is_valid():
            try:
                direct_video_url = None
                video_title = form.cleaned_data.get('title', '').strip()
                
                if approved_app.channel_type == 'tiktok':
                    from .utils import extract_tiktok_video_url, fetch_tiktok_video_title
                    video_data = extract_tiktok_video_url(form.cleaned_data['video_url'])
                    if video_data.get('video_url') and not video_data.get('error'):
                        direct_video_url = video_data['video_url']
                        logger.info("Extracted TikTok direct video URL for edit submission")
                    else:
                        logger.warning(f"Could not extract TikTok video URL: {video_data.get('error', 'Unknown error')}")
                    
                    if not video_title:
                        fetched_title = fetch_tiktok_video_title(form.cleaned_data['video_url'])
                        if fetched_title:
                            video_title = fetched_title
                            logger.info(f"Auto-fetched TikTok video title: {video_title}")
                
                from .utils import get_fallback_thumbnail
                # Use fallback to ensure we have a valid thumbnail
                existing_thumb = ''  # No existing thumbnail for new submission
                new_thumb = (approved_app.channel_thumbnail or '').strip()
                best_thumb = get_fallback_thumbnail(existing_thumb, new_thumb)
                
                submission = EditSubmission(
                    user=request.user,
                    approved_application=approved_app,
                    channel_link=approved_app.channel_link,
                    channel_type=approved_app.channel_type,
                    channel_name=approved_app.channel_name,
                    channel_thumbnail=best_thumb,
                    scheduled_week=next_week_start,
                    video_url=form.cleaned_data['video_url'],
                    direct_video_url=direct_video_url,
                    title=video_title,
                    description=form.cleaned_data.get('description', ''),
                    status='pending'  # Save as pending until user confirms
                )
                submission.save()
                
                # Redirect to preview page
                return redirect('edithub:preview_edit_submission', pk=submission.pk)
            
            except Exception as error:
                logger.error("Error creating edit submission", exc_info=True)
                messages.error(request, f"An error occurred: {error}")
        
        if platform == 'youtube':
            youtube_form = form
            tiktok_form = EditSubmissionForm(approved_application=tiktok_app) if tiktok_app and not tiktok_future_submission else None
        else:
            tiktok_form = form
            youtube_form = EditSubmissionForm(approved_application=youtube_app) if youtube_app and not youtube_future_submission else None
    else:
        if youtube_app and not youtube_future_submission:
            youtube_form = EditSubmissionForm(approved_application=youtube_app)
        if tiktok_app and not tiktok_future_submission:
            tiktok_form = EditSubmissionForm(approved_application=tiktok_app)
    
    default_platform = 'youtube' if youtube_app else 'tiktok'
    if not youtube_app and tiktok_app:
        default_platform = 'tiktok'
    
    return render(request, 'edithub/submit_edit.html', {
        'youtube_form': youtube_form,
        'tiktok_form': tiktok_form,
        'youtube_app': youtube_app,
        'tiktok_app': tiktok_app,
        'youtube_future_submission': youtube_future_submission,
        'tiktok_future_submission': tiktok_future_submission,
        'target_week_label': next_week_label,
        'target_week_start': next_week_start,
        'target_week_end': next_week_end,
        'default_platform': default_platform,
        'can_edit_delete': can_edit_delete,
        'deadline': deadline,
    })


@login_required
def edit_submission(request, pk):
    """Edit an existing edit submission before the deadline"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can edit submissions.")
        return redirect('edithub:ranking_table')
    
    try:
        submission = EditSubmission.objects.get(pk=pk, user=request.user)
    except EditSubmission.DoesNotExist:
        messages.error(request, "Submission not found.")
        return redirect('edithub:submit_edit')
    
    # For pending submissions, allow editing without deadline check
    is_pending = submission.status == 'pending'
    deadline = None
    
    # Check if we're before the deadline (only for verified submissions)
    if not is_pending:
        from datetime import datetime, timezone as dt_timezone
        from .utils import get_week_start_end
        now = datetime.now(dt_timezone.utc)
        if submission.scheduled_week:
            deadline = datetime.combine(submission.scheduled_week, datetime.min.time()).replace(tzinfo=dt_timezone.utc)
        else:
            # Fallback: use next week start
            week_start_dt, _ = get_week_start_end()
            deadline = (week_start_dt + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        if now >= deadline:
            messages.error(request, "The deadline has passed. You can no longer edit this submission.")
            return redirect('edithub:submit_edit')
    else:
        # For pending submissions, calculate deadline for display purposes
        from datetime import datetime, timezone as dt_timezone
        from .utils import get_week_start_end
        if submission.scheduled_week:
            deadline = datetime.combine(submission.scheduled_week, datetime.min.time()).replace(tzinfo=dt_timezone.utc)
        else:
            week_start_dt, _ = get_week_start_end()
            deadline = (week_start_dt + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    approved_app = submission.approved_application
    if not approved_app:
        messages.error(request, "Cannot edit submission without an approved application.")
        return redirect('edithub:submit_edit')
    
    if request.method == 'POST':
        form = EditSubmissionForm(data=request.POST, files=request.FILES, approved_application=approved_app, instance=submission)
        
        if form.is_valid():
            try:
                direct_video_url = submission.direct_video_url
                video_title = form.cleaned_data.get('title', '').strip()
                
                if approved_app.channel_type == 'tiktok':
                    from .utils import extract_tiktok_video_url, fetch_tiktok_video_title
                    video_data = extract_tiktok_video_url(form.cleaned_data['video_url'])
                    if video_data.get('video_url') and not video_data.get('error'):
                        direct_video_url = video_data['video_url']
                    if not video_title:
                        fetched_title = fetch_tiktok_video_title(form.cleaned_data['video_url'])
                        if fetched_title:
                            video_title = fetched_title
                
                submission.video_url = form.cleaned_data['video_url']
                submission.direct_video_url = direct_video_url
                submission.title = video_title
                submission.description = form.cleaned_data.get('description', '')
                # Update channel thumbnail if needed
                from .utils import get_fallback_thumbnail
                existing_thumb = (submission.channel_thumbnail or '').strip()
                new_thumb = (approved_app.channel_thumbnail or '').strip()
                best_thumb = get_fallback_thumbnail(existing_thumb, new_thumb)
                submission.channel_thumbnail = best_thumb
                
                submission.save()
                
                # If pending, redirect back to preview; otherwise redirect to submit_edit
                if submission.status == 'pending':
                    messages.success(request, f"Edit updated successfully! Please review and confirm your submission.")
                    return redirect('edithub:preview_edit_submission', pk=submission.pk)
                else:
                    messages.success(request, f"Edit updated successfully for {approved_app.get_channel_type_display()}!")
                    return redirect('edithub:submit_edit')
            
            except Exception as error:
                logger.error("Error updating edit submission", exc_info=True)
                messages.error(request, f"An error occurred: {error}")
    else:
        form = EditSubmissionForm(approved_application=approved_app, instance=submission)
    
    week_start_dt, _ = get_week_start_end()
    next_week_start = (week_start_dt + timedelta(days=7)).date()
    next_week_end = next_week_start + timedelta(days=4)
    next_week_label = f"{next_week_start.strftime('%b %d')} – {next_week_end.strftime('%b %d')}"
    
    return render(request, 'edithub/edit_submission.html', {
        'form': form,
        'submission': submission,
        'approved_app': approved_app,
        'target_week_label': next_week_label,
        'deadline': deadline,
    })


@login_required
@require_http_methods(["POST"])
def delete_submission(request, pk):
    """Delete an edit submission before the deadline"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can delete submissions.")
        return redirect('edithub:ranking_table')
    
    try:
        submission = EditSubmission.objects.get(pk=pk, user=request.user)
    except EditSubmission.DoesNotExist:
        messages.error(request, "Submission not found.")
        return redirect('edithub:submit_edit')
    
    # Check if we're before the deadline
    from datetime import datetime, timezone
    from .utils import get_week_start_end
    now = datetime.now(timezone.utc)
    if submission.scheduled_week:
        deadline = datetime.combine(submission.scheduled_week, datetime.min.time()).replace(tzinfo=timezone.utc)
    else:
        week_start_dt, _ = get_week_start_end()
        deadline = (week_start_dt + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    if now >= deadline:
        messages.error(request, "The deadline has passed. You can no longer delete this submission.")
        return redirect('edithub:submit_edit')
    
    platform = submission.channel_type
    submission.delete()
    messages.success(request, f"Your {platform.title()} edit submission has been deleted.")
    return redirect('edithub:submit_edit')


@login_required
def preview_edit_submission(request, pk):
    """Step 2: Preview the video before confirming submission"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can submit edits.")
        return redirect('edithub:ranking_table')
    
    from django.utils import timezone as django_timezone
    
    try:
        submission = EditSubmission.objects.get(pk=pk, user=request.user, status='pending')
    except EditSubmission.DoesNotExist:
        messages.error(request, "Submission not found or already confirmed.")
        return redirect('edithub:submit_edit')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirm':
            # Confirm the submission - mark as verified
            submission.status = 'verified'
            submission.verified_date = django_timezone.now()
            submission.save()
            
            messages.success(request, f"Edit submitted successfully for {submission.get_channel_type_display()}! It will participate in the week of {submission.scheduled_week.strftime('%b %d')}.")
            return redirect('edithub:edit_submission_success', pk=submission.pk)
        
        elif action == 'edit':
            # Go back to edit the submission
            return redirect('edithub:edit_submission', pk=submission.pk)
        
        elif action == 'cancel':
            # Cancel and delete the submission
            submission.delete()
            messages.info(request, "Submission cancelled.")
            return redirect('edithub:submit_edit')
    
    from .utils import get_week_start_end
    week_start_dt, _ = get_week_start_end()
    next_week_start = (week_start_dt + timedelta(days=7)).date()
    next_week_end = next_week_start + timedelta(days=4)
    next_week_label = f"{next_week_start.strftime('%b %d')} – {next_week_end.strftime('%b %d')}"
    
    return render(request, 'edithub/preview_edit_submission.html', {
        'submission': submission,
        'target_week_label': next_week_label,
    })


@login_required
def edit_submission_success(request, pk):
    """Step 3: Success page after confirming submission"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can submit edits.")
        return redirect('edithub:ranking_table')
    
    try:
        submission = EditSubmission.objects.get(pk=pk, user=request.user, status='verified')
    except EditSubmission.DoesNotExist:
        messages.error(request, "Submission not found.")
        return redirect('edithub:submit_edit')
    
    # Check if we're before the deadline (before Monday 00:00 of next week)
    from datetime import datetime, timezone as dt_timezone
    from .utils import get_week_start_end
    now = datetime.now(dt_timezone.utc)
    if submission.scheduled_week:
        deadline = datetime.combine(submission.scheduled_week, datetime.min.time()).replace(tzinfo=dt_timezone.utc)
    else:
        week_start_dt, _ = get_week_start_end()
        deadline = (week_start_dt + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    can_edit_delete = now < deadline
    
    week_start_dt, _ = get_week_start_end()
    next_week_start = (week_start_dt + timedelta(days=7)).date()
    next_week_end = next_week_start + timedelta(days=4)
    next_week_label = f"{next_week_start.strftime('%b %d')} – {next_week_end.strftime('%b %d')}"
    
    return render(request, 'edithub/edit_submission_success.html', {
        'submission': submission,
        'target_week_label': next_week_label,
        'can_edit_delete': can_edit_delete,
        'deadline': deadline,
    })


@login_required
def confirm_edit_submission(request):
    """Confirmation page after edit submission"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can submit edits.")
        return redirect('edithub:ranking_table')
    
    submission_id = request.session.get('pending_edit_submission_id')
    
    if not submission_id:
        messages.error(request, "No submission data found. Please start over.")
        return redirect('edithub:submit_edit')
    
    try:
        submission = EditSubmission.objects.get(pk=submission_id, user=request.user)
    except EditSubmission.DoesNotExist:
        messages.error(request, "Submission not found. Please start over.")
        request.session.pop('pending_edit_submission_id', None)
        return redirect('edithub:submit_edit')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirm':
            submission.channel_verified = True
            submission.status = 'verified'
            from django.utils import timezone
            submission.verified_date = timezone.now()
            submission.save()
            
            request.session.pop('pending_edit_submission_id', None)
            messages.success(request, "Edit submitted successfully! It will be visible in the Edit of the Week section.")
            return redirect('edithub:view_all_edits')
        
        # Cancel action
        submission.delete()
        request.session.pop('pending_edit_submission_id', None)
        messages.info(request, "Submission cancelled.")
        return redirect('edithub:submit_edit')
    
    context = {
        'submission': submission,
    }
    return render(request, 'edithub/confirm_edit_submission.html', context)


def view_all_edits(request):
    """View all edits (YouTube Shorts-like interface)"""
    # Get platform filter from query parameter (default to 'youtube')
    platform = request.GET.get('platform', 'youtube')
    if platform not in ['youtube', 'tiktok']:
        platform = 'youtube'
    
    week_start_dt, week_end_dt = get_week_start_end()  # Current week (Mon-Sun)
    competition_state = get_competition_state()
    
    # Show CURRENT week's edits (Mon-Sun)
    # Display edits scheduled for the current week
    display_week_start_dt = week_start_dt  # Current week Monday
    display_week_end_dt = week_start_dt + timedelta(days=6, hours=23, minutes=59, seconds=59)  # Current week Sunday
    display_week_date = display_week_start_dt.date()
    display_week_label = f"{display_week_start_dt.strftime('%b %d')} – {display_week_end_dt.strftime('%b %d')}"
    
    # Get verified edits filtered by platform and ordered by calculated points
    # Show edits from the full week (Mon-Sun)
    edits_qs = EditSubmission.objects.filter(
        status='verified',
        channel_type=platform
    ).filter(
        Q(scheduled_week=display_week_date) |
        (Q(scheduled_week__isnull=True) & Q(submitted_date__gte=display_week_start_dt) & Q(submitted_date__lte=display_week_end_dt))
    ).order_by('-calculated_points', 'submitted_date')
    
    # Pagination: 1 video per page (to avoid multiple videos playing simultaneously)
    paginator = Paginator(edits_qs, 1)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get user's upvoted edits if authenticated
    user_upvoted_ids = set()
    user_upvote_count = 0
    if request.user.is_authenticated:
        user_upvotes = EditUpvote.objects.filter(
            user=request.user,
            is_active=True
        ).select_related('edit_submission')
        user_upvoted_ids = {upvote.edit_submission_id for upvote in user_upvotes}
        user_upvote_count = len(user_upvoted_ids)
    
    # Enrich current page with thumbnails and TikTok embed HTML
    from .utils import fetch_tiktok_oembed, youtube_thumbnail_from_url
    enriched_page = []
    for e in page_obj.object_list:
        if e.channel_type == 'youtube':
            thumb = youtube_thumbnail_from_url(e.video_url)
            embed_html = None
        else:
            oembed_data = fetch_tiktok_oembed(e.video_url)
            thumb = oembed_data.get('thumbnail_url')
            embed_html = oembed_data.get('html')  # Get TikTok's official embed HTML
        
        enriched_page.append({
            'instance': e,
            'id': e.id,
            'video_url': e.video_url,
            'direct_video_url': getattr(e, 'direct_video_url', None),  # For TikTok HTML5 video player (deprecated, using embed now)
            'tiktok_embed_html': embed_html,  # TikTok's official embed HTML from oEmbed API
            'channel_type': e.channel_type,
            'channel_name': e.channel_name,
            'channel_thumbnail': e.channel_thumbnail,
            'title': getattr(e, 'title', ''),
            'upvote_count': e.upvote_count,
            'calculated_points': float(e.calculated_points),
            'thumbnail_url': thumb,
        })

    # Get ALL edits for ranking panel filtered by platform (with channel thumbnails)
    # Show ALL edits from the current week (Mon-Sun) - no limit, show complete rankings
    all_edits_ranking = list(EditSubmission.objects.filter(
        status='verified',
        channel_type=platform
    ).filter(
        Q(scheduled_week=display_week_date) |
        (Q(scheduled_week__isnull=True) & Q(submitted_date__gte=display_week_start_dt) & Q(submitted_date__lte=display_week_end_dt))
    ).order_by('-calculated_points', 'submitted_date').values('id', 'title', 'channel_name', 'calculated_points', 'upvote_count', 'channel_type', 'channel_thumbnail'))  # Show all edits, no limit
    
    # Get channel statistics for banner (if viewing a specific edit)
    channel_stats = None
    current_edit = None
    if enriched_page:
        current_edit = enriched_page[0]['instance']
        edit_user = current_edit.user
        
        # Calculate user statistics (for modal popup)
        total_edits = EditSubmission.objects.filter(
            user=edit_user,
            status='verified'
        ).count()
        
        # Count Edit of the Week wins (top 3 finishes)
        edit_of_week_wins = EditSubmission.objects.filter(
            user=edit_user,
            status='verified',
            week_rank__in=[1, 2, 3]
        ).count()
        
        # Count Edit of the Month wins (top edit in a calendar month)
        from django.utils import timezone
        from datetime import datetime
        from calendar import monthrange
        
        edit_of_month_wins = 0
        # Get all unique year-month combinations where user had verified edits
        user_edits = EditSubmission.objects.filter(
            user=edit_user,
            status='verified'
        ).order_by('scheduled_week', 'submitted_date')
        
        # Group edits by year-month
        months_checked = set()
        for edit in user_edits:
            reference_date = edit.scheduled_week or edit.submitted_date.date()
            year_month = (reference_date.year, reference_date.month)
            if year_month in months_checked:
                continue
            months_checked.add(year_month)
            
            # Get first and last day of that month
            first_day = datetime(year_month[0], year_month[1], 1, tzinfo=timezone.utc)
            last_day_num = monthrange(year_month[0], year_month[1])[1]
            last_day = datetime(year_month[0], year_month[1], last_day_num, 23, 59, 59, tzinfo=timezone.utc)
            
            # Get the highest points edit in that month (across all users)
            top_edit = EditSubmission.objects.filter(
                status='verified',
                scheduled_week__gte=first_day.date(),
                scheduled_week__lte=last_day.date()
            ).order_by('-calculated_points', 'submitted_date').first()
            
            # If this user's edit is the top edit of the month, count it as a win
            if top_edit and top_edit.user == edit_user:
                edit_of_month_wins += 1
        
        # Get user's best rank (only from weeks that have started)
        from datetime import date
        today = date.today()
        best_rank = EditSubmission.objects.filter(
            user=edit_user,
            status='verified',
            scheduled_week__lte=today  # Only count points from weeks that have started
        ).order_by('-calculated_points').first()
        best_points = best_rank.calculated_points if best_rank else 0
        
        # Get mix rank and editor title from EditorApplication
        mix_rank = None
        editor_title = f"{current_edit.channel_type.title()} Editor"  # Default
        editor_title_rarity = 'ordinary'  # Default
        
        try:
            # Get the user's EditorApplication(s) - they might have multiple (YouTube and TikTok)
            # For mix ranking, we use the one with highest follower count
            # For title, use the one matching the edit's channel type
            editor_app_for_title = EditorApplication.objects.filter(
                user=edit_user,
                status='accepted',
                removal_requested=False,
                channel_type=current_edit.channel_type
            ).first()
            
            if editor_app_for_title:
                editor_title = editor_app_for_title.editor_title
                editor_title_rarity = editor_app_for_title.editor_title_rarity
            
            # For mix rank, use the one with highest follower count
            editor_app = EditorApplication.objects.filter(
                user=edit_user,
                status='accepted',
                removal_requested=False
            ).order_by('-follower_count').first()
            
            if editor_app and editor_app.rank_position:
                mix_rank = editor_app.rank_position
        except Exception:
            pass
        
        # Use channel thumbnail and channel name from the edit (YouTube/TikTok profile)
        channel_stats = {
            'user': edit_user,
            'total_edits': total_edits,
            'edit_of_week_wins': edit_of_week_wins,
            'edit_of_month_wins': edit_of_month_wins,
            'best_points': float(best_points),
            'profile_picture': current_edit.channel_thumbnail,  # Use YouTube/TikTok thumbnail
            'username': current_edit.channel_name,  # Use YouTube/TikTok channel name
            'channel_type': current_edit.channel_type,
            'editor_title': editor_title,  # Customizable editor title
            'editor_title_rarity': editor_title_rarity,  # Include rarity for styling
            'mix_rank': mix_rank,  # Rank in mix (overall) editors table
        }
    
    context = {
        'edits': enriched_page,
        'current_edit': current_edit,  # Single edit for current page
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'user_upvoted_ids': user_upvoted_ids,
        'user_upvote_count': user_upvote_count,
        'max_upvotes': 3,
        'all_edits_ranking': all_edits_ranking,  # For side panel
        'current_platform': platform,  # Current selected platform
        'display_week_label': display_week_label,
        'display_week_start': display_week_date,
        'competition_state': competition_state,  # Competition state (live/results)
        'channel_stats': channel_stats,  # Channel statistics for banner (YouTube/TikTok profile)
    }
    
    return render(request, 'edithub/view_all_edits.html', context)


@login_required
@require_http_methods(["POST"])
def upvote_edit(request, pk):
    """AJAX endpoint to upvote an edit"""
    if request.user.role != 'user':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        submission = EditSubmission.objects.get(pk=pk, status='verified')
    except EditSubmission.DoesNotExist:
        return JsonResponse({'error': 'Edit not found'}, status=404)
    
    # Check if user is trying to upvote their own edit
    if submission.user == request.user:
        return JsonResponse({
            'error': 'You cannot upvote your own edit.',
            'self_upvote': True
        }, status=400)
    
    # Check if user has reached max upvotes (3)
    user_upvote_count = EditUpvote.objects.filter(user=request.user, is_active=True).count()
    if user_upvote_count >= 3:
        # Check if this edit is already upvoted
        existing_upvote = EditUpvote.objects.filter(
            user=request.user,
            edit_submission=submission,
            is_active=True
        ).first()
        
        if not existing_upvote:
            return JsonResponse({
                'error': 'You have reached the maximum of 3 upvotes. Please remove an upvote first.',
                'max_reached': True
            }, status=400)
    
    # Toggle upvote
    upvote, created = EditUpvote.objects.get_or_create(
        user=request.user,
        edit_submission=submission,
        defaults={'is_active': True}
    )
    
    if not created:
        # Toggle existing upvote
        upvote.is_active = not upvote.is_active
        upvote.save()
    
    submission.update_upvote_count()
    # Refresh from DB to get updated calculated_points
    submission.refresh_from_db()
    
    return JsonResponse({
        'success': True,
        'upvoted': upvote.is_active,
        'upvote_count': submission.upvote_count,
        'calculated_points': float(submission.calculated_points),
        'user_upvote_count': EditUpvote.objects.filter(user=request.user, is_active=True).count()
    })


@login_required
@require_http_methods(["POST"])
def report_edit(request, pk):
    """AJAX endpoint to report an edit"""
    if request.user.role != 'user':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        submission = EditSubmission.objects.get(pk=pk, status='verified')
    except EditSubmission.DoesNotExist:
        return JsonResponse({'error': 'Edit not found'}, status=404)
    
    # Check if user already reported this edit
    existing_report = EditReport.objects.filter(
        user=request.user,
        edit_submission=submission,
        is_active=True
    ).first()
    
    if existing_report:
        return JsonResponse({'error': 'You have already reported this edit.'}, status=400)
    
    form = EditReportForm(request.POST)
    if form.is_valid():
        report = EditReport(
            user=request.user,
            edit_submission=submission,
            reason=form.cleaned_data['reason'],
            description=form.cleaned_data.get('description', ''),
            is_active=True
        )
        report.save()
        
        submission.update_report_count()
        
        return JsonResponse({
            'success': True,
            'message': 'Edit reported successfully. Thank you for helping keep the community safe.'
        })
    
    return JsonResponse({'error': 'Invalid form data', 'errors': form.errors}, status=400)


@login_required
def admin_reported_edits(request):
    """Admin view to see and manage reported edits"""
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin account required.")
        return redirect('home')
    
    # Get all active reports
    reports = EditReport.objects.filter(
        is_active=True,
        is_resolved=False
    ).select_related('user', 'edit_submission').order_by('-created_date')
    
    # Filter by reason if provided
    reason_filter = request.GET.get('reason', 'all')
    if reason_filter != 'all':
        reports = reports.filter(reason=reason_filter)
    
    # Pagination
    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'reports': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'reason_filter': reason_filter,
        'reason_choices': EditReport.REPORT_REASON_CHOICES,
        'total_reports': EditReport.objects.filter(is_active=True, is_resolved=False).count(),
    }
    
    return render(request, 'edithub/admin_reported_edits.html', context)


@login_required
@require_http_methods(["POST"])
def admin_resolve_report(request, pk):
    """Admin endpoint to resolve/remove reported edits"""
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        report = EditReport.objects.get(pk=pk)
    except EditReport.DoesNotExist:
        return JsonResponse({'error': 'Report not found'}, status=404)
    
    action = request.POST.get('action')
    
    if action == 'remove_edit':
        # Remove the edit submission
        report.edit_submission.status = 'rejected'
        report.edit_submission.save()
        report.is_resolved = True
        report.resolved_by = request.user
        from django.utils import timezone
        report.resolved_date = timezone.now()
        report.save()
        
        messages.success(request, "Edit removed successfully.")
    
    elif action == 'dismiss_report':
        # Dismiss the report (mark as resolved but keep edit)
        report.is_resolved = True
        report.resolved_by = request.user
        from django.utils import timezone
        report.resolved_date = timezone.now()
        report.save()
        
        messages.success(request, "Report dismissed.")
    
    else:
        return JsonResponse({'error': 'Invalid action'}, status=400)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect('edithub:admin_reported_edits')


def tournament_matches(request):
    """View to list all tournament matches"""
    active_tournament = Tournament.get_active_tournament()
    matches = []
    
    if active_tournament:
        raw_matches = active_tournament.get_match_pairs()
        # Add display names for match types
        match_type_display = {
            'semi_final_1': 'Semi-Final 1',
            'semi_final_2': 'Semi-Final 2',
            'final': 'Final',
        }
        for match in raw_matches:
            match['type_display'] = match_type_display.get(match['type'], match['type'].replace('_', ' ').title())
            # Prepare participant data for display
            def prepare_participant_data(participant):
                if not participant:
                    return None
                
                return {
                    'user': participant.user,
                    'app': participant,
                    'channel_name': participant.channel_name or participant.user.username,
                    'username': participant.user.username,
                    'profile_picture': participant.user.profile_picture.url if participant.user.profile_picture else None,
                    'channel_thumbnail': (participant.channel_thumbnail or '').strip(),
                    'channel_type': participant.channel_type,
                    'editor_title': participant.editor_title,  # Use property which handles custom titles
                    'editor_title_rarity': participant.editor_title_rarity,  # Include rarity for styling
                }
            
            match['participant_1'] = prepare_participant_data(match['participant_1'])
            match['participant_2'] = prepare_participant_data(match['participant_2'])
            matches.append(match)
    
    context = {
        'tournament': active_tournament,
        'matches': matches,
    }
    
    return render(request, 'edithub/tournament_matches.html', context)


def tournament_match_detail(request, match_type):
    """View to show a specific tournament match (The Fish Food Show)"""
    active_tournament = Tournament.get_active_tournament()
    
    if not active_tournament:
        messages.error(request, 'No active tournament found.')
        return redirect('edithub:ranking_table')
    
    # Get match data based on match_type
    match_data = None
    if match_type == 'semi_final_1' and active_tournament.semi_finals_active:
        if active_tournament.participant_1 and active_tournament.participant_2:
            match_data = {
                'type': 'semi_final_1',
                'type_display': 'Semi-Final 1',
                'participant_1': active_tournament.participant_1,
                'participant_1_edit_link': active_tournament.participant_1_edit_link,
                'participant_2': active_tournament.participant_2,
                'participant_2_edit_link': active_tournament.participant_2_edit_link,
            }
    elif match_type == 'semi_final_2' and active_tournament.semi_finals_active:
        if active_tournament.participant_3 and active_tournament.participant_4:
            match_data = {
                'type': 'semi_final_2',
                'type_display': 'Semi-Final 2',
                'participant_1': active_tournament.participant_3,
                'participant_1_edit_link': active_tournament.participant_3_edit_link,
                'participant_2': active_tournament.participant_4,
                'participant_2_edit_link': active_tournament.participant_4_edit_link,
            }
    elif match_type == 'final' and active_tournament.finals_active:
        if active_tournament.finalist_1 and active_tournament.finalist_2:
            match_data = {
                'type': 'final',
                'type_display': 'Final',
                'participant_1': active_tournament.finalist_1,
                'participant_1_edit_link': active_tournament.finalist_1_edit_link,
                'participant_2': active_tournament.finalist_2,
                'participant_2_edit_link': active_tournament.finalist_2_edit_link,
            }
    
    if not match_data:
        messages.error(request, 'Match not found or not available.')
        return redirect('edithub:ranking_table')
    
    # Get vote counts
    votes_participant_1 = TournamentMatchVote.objects.filter(
        tournament=active_tournament,
        match_type=match_type,
        voted_for=match_data['participant_1']
    ).count()
    
    votes_participant_2 = TournamentMatchVote.objects.filter(
        tournament=active_tournament,
        match_type=match_type,
        voted_for=match_data['participant_2']
    ).count()
    
    # Check if user has already voted
    user_vote = None
    if request.user.is_authenticated:
        try:
            user_vote = TournamentMatchVote.objects.get(
                tournament=active_tournament,
                match_type=match_type,
                voter=request.user
            )
        except TournamentMatchVote.DoesNotExist:
            pass
    
    # Prepare participant data
    def prepare_participant_data(participant, edit_link):
        if not participant:
            return None
        
        # Determine if edit link is YouTube or TikTok
        is_youtube = False
        is_tiktok = False
        if edit_link:
            if 'youtube.com' in edit_link or 'youtu.be' in edit_link:
                is_youtube = True
            elif 'tiktok.com' in edit_link:
                is_tiktok = True
        
        return {
            'user': participant.user,
            'app': participant,
            'channel_name': participant.channel_name or participant.user.username,
            'username': participant.user.username,
            'profile_picture': participant.user.profile_picture.url if participant.user.profile_picture else None,
            'channel_thumbnail': (participant.channel_thumbnail or '').strip(),
            'channel_type': participant.channel_type,
            'editor_title': participant.editor_title,  # Use property which handles custom titles
            'editor_title_rarity': participant.editor_title_rarity,  # Include rarity for styling
            'edit_link': edit_link,
            'is_youtube': is_youtube,
            'is_tiktok': is_tiktok,
        }
    
    participant_1_data = prepare_participant_data(match_data['participant_1'], match_data['participant_1_edit_link'])
    participant_2_data = prepare_participant_data(match_data['participant_2'], match_data['participant_2_edit_link'])
    
    # Determine next and previous matches (circular navigation)
    all_matches = active_tournament.get_match_pairs()
    next_match = None
    previous_match = None
    current_match_index = -1
    
    # Find current match index
    for idx, match in enumerate(all_matches):
        if match['type'] == match_type:
            current_match_index = idx
            break
    
    # Get next and previous matches (circular - wraps around)
    if current_match_index >= 0 and len(all_matches) > 0:
        # Next match (wraps to first if on last)
        next_match = all_matches[(current_match_index + 1) % len(all_matches)]
        # Previous match (wraps to last if on first)
        previous_match = all_matches[(current_match_index - 1) % len(all_matches)]
    
    context = {
        'tournament': active_tournament,
        'match_type': match_type,
        'match_type_display': match_data['type_display'],
        'participant_1': participant_1_data,
        'participant_2': participant_2_data,
        'votes_participant_1': votes_participant_1,
        'votes_participant_2': votes_participant_2,
        'user_vote': user_vote,
        'user_has_voted': user_vote is not None,
        'next_match': next_match,
        'previous_match': previous_match,
    }
    
    return render(request, 'edithub/tournament_match_detail.html', context)


@login_required
@require_http_methods(["POST"])
def vote_tournament_match(request, match_type):
    """AJAX endpoint to vote for a tournament match"""
    active_tournament = Tournament.get_active_tournament()
    
    if not active_tournament:
        return JsonResponse({'success': False, 'error': 'No active tournament found.'}, status=404)
    
    # Validate match_type
    valid_match_types = ['semi_final_1', 'semi_final_2', 'final']
    if match_type not in valid_match_types:
        return JsonResponse({'success': False, 'error': 'Invalid match type.'}, status=400)
    
    # Check if match is active
    if match_type in ['semi_final_1', 'semi_final_2'] and not active_tournament.semi_finals_active:
        return JsonResponse({'success': False, 'error': 'Semi-finals are not active.'}, status=400)
    if match_type == 'final' and not active_tournament.finals_active:
        return JsonResponse({'success': False, 'error': 'Finals are not active.'}, status=400)
    
    # Get the participant being voted for
    participant_id = request.POST.get('participant_id')
    if not participant_id:
        return JsonResponse({'success': False, 'error': 'Participant ID is required.'}, status=400)
    
    try:
        participant = EditorApplication.objects.get(pk=participant_id)
    except EditorApplication.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Participant not found.'}, status=404)
    
    # Check if user has already voted
    existing_vote = TournamentMatchVote.objects.filter(
        tournament=active_tournament,
        match_type=match_type,
        voter=request.user
    ).first()
    
    if existing_vote:
        return JsonResponse({'success': False, 'error': 'You have already voted for this match.'}, status=400)
    
    # Verify participant is in this match
    valid_participants = []
    if match_type == 'semi_final_1':
        valid_participants = [active_tournament.participant_1, active_tournament.participant_2]
    elif match_type == 'semi_final_2':
        valid_participants = [active_tournament.participant_3, active_tournament.participant_4]
    elif match_type == 'final':
        valid_participants = [active_tournament.finalist_1, active_tournament.finalist_2]
    
    if participant not in valid_participants:
        return JsonResponse({'success': False, 'error': 'Invalid participant for this match.'}, status=400)
    
    # Create vote
    try:
        vote = TournamentMatchVote.objects.create(
            tournament=active_tournament,
            match_type=match_type,
            voter=request.user,
            voted_for=participant
        )
    except Exception as e:
        logger.error(f"Error creating vote: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'Failed to record vote: {str(e)}'
        }, status=500)
    
    # Get updated vote counts
    try:
        votes_participant_1 = TournamentMatchVote.objects.filter(
            tournament=active_tournament,
            match_type=match_type,
            voted_for=valid_participants[0]
        ).count()
        
        votes_participant_2 = TournamentMatchVote.objects.filter(
            tournament=active_tournament,
            match_type=match_type,
            voted_for=valid_participants[1]
        ).count()
    except Exception as e:
        logger.error(f"Error getting vote counts: {str(e)}")
        # Still return success but with error in counts
        votes_participant_1 = 0
        votes_participant_2 = 0
    
    return JsonResponse({
        'success': True,
        'message': 'Vote recorded successfully!',
        'votes_participant_1': votes_participant_1,
        'votes_participant_2': votes_participant_2,
        'voted_for_id': participant.id,
    })
