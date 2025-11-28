from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from events.models import Event, EventApplication,EventFieldResponse
from django.contrib.auth import get_user_model
from events.forms import EventApplicationForm
from django.db.models import Case, When, Value, IntegerField, Max, Sum, Q
from datetime import datetime, timedelta, timezone



User = get_user_model()

def home(request):
    return render(request, 'dashboard/home.html')

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        messages.error(request, "Access denied. Admin account required.")
        return redirect('home')

    hosted_events = Event.objects.filter(created_by=request.user)
    recent_applications = EventApplication.objects.filter(event__created_by=request.user)

    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter in ['pending', 'accepted', 'rejected']:
        recent_applications = recent_applications.filter(status=status_filter)

    # Order by date
    date_order = request.GET.get('date_order')
    if date_order == 'oldest':
        recent_applications = recent_applications.order_by('applied_date')
    else:
        recent_applications = recent_applications.order_by('-applied_date')  # Default to newest

    context = {
        'hosted_events': hosted_events,
        'recent_applications': recent_applications,
        'total_events': hosted_events.count(),
        'total_applications': EventApplication.objects.filter(event__created_by=request.user).count(),
        'pending_applications': EventApplication.objects.filter(event__created_by=request.user, status='pending'),  # ✅ Added this
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


@login_required
def user_dashboard(request):
    if request.user.role != 'user':
        messages.error(request, "Access denied. User account required.")
        return redirect('home')

    applications = EventApplication.objects.filter(applicant=request.user).order_by('-applied_date')
    
    # Get EditingHub application status
    from edithub.models import EditorApplication, EditSubmission
    editor_applications = EditorApplication.objects.filter(user=request.user).order_by('-applied_date')
    
    # Separate applications by platform
    youtube_application = editor_applications.filter(channel_type='youtube').first()
    tiktok_application = editor_applications.filter(channel_type='tiktok').first()
    
    # Get the first application (for backward compatibility)
    editor_application = editor_applications.first() if editor_applications.exists() else None
    
    # Get primary application (highest follower count) for title display
    primary_app = EditorApplication.objects.filter(
        user=request.user,
        status='accepted'
    ).order_by('-follower_count').first()
    
    # Calculate user's ranking position for each platform (if accepted)
    youtube_rank = None
    tiktok_rank = None
    
    if youtube_application and youtube_application.status == 'accepted':
        # Get all accepted YouTube applications ordered by follower count
        all_youtube = EditorApplication.objects.filter(
            channel_type='youtube',
            status='accepted',
            removal_requested=False
        ).order_by('-follower_count', 'applied_date')
        for index, app in enumerate(all_youtube, start=1):
            if app.user_id == request.user.id:
                youtube_rank = index
                break
    
    if tiktok_application and tiktok_application.status == 'accepted':
        # Get all accepted TikTok applications ordered by follower count
        all_tiktok = EditorApplication.objects.filter(
            channel_type='tiktok',
            status='accepted',
            removal_requested=False
        ).order_by('-follower_count', 'applied_date')
        for index, app in enumerate(all_tiktok, start=1):
            if app.user_id == request.user.id:
                tiktok_rank = index
                break
    
    # Get ranking tab selection (default to 'mix')
    ranking_tab = request.GET.get('ranking_tab', 'mix')
    if ranking_tab not in ['mix', 'youtube', 'tiktok']:
        ranking_tab = 'mix'
    
    # Helper function to get ranking data for a specific tab
    def get_ranking_data(tab_type):
        user_rank = None
        user_rank_app = None
        rank_above = None
        rank_below = None
        
        # EditorApplication is already imported at function scope (line 57)
        # Use it directly without re-importing
        
        if tab_type == 'mix':
            # Mix ranking: group by user and sum followers from both platforms
            # For users with both YouTube and TikTok, sum the followers
            # For users with only one platform, use that platform's followers
            from django.db.models import Sum
            
            # Get all users with accepted applications
            users_with_apps = EditorApplication.objects.filter(
                status='accepted',
                removal_requested=False
            ).values('user_id').distinct()
            
            user_totals = []
            for user_data in users_with_apps:
                user_id = user_data['user_id']
                # Get all applications for this user
                user_apps = EditorApplication.objects.filter(
                    user_id=user_id,
                    status='accepted',
                    removal_requested=False
                ).select_related('user')
                
                # Sum followers from all platforms
                total_followers = sum(app.follower_count for app in user_apps)
                
                # Get the primary app (highest follower count) for display purposes
                primary_app = max(user_apps, key=lambda x: x.follower_count)
                
                # Get earliest applied_date for tie-breaking
                earliest_app = min(user_apps, key=lambda x: x.applied_date)
                
                user_totals.append({
                    'user_id': user_id,
                    'total_followers': total_followers,
                    'app': primary_app,
                    'applied_date': earliest_app.applied_date
                })
            
            # Sort by total followers (descending), then by applied_date (ascending)
            sorted_users = sorted(
                user_totals, 
                key=lambda x: (-x['total_followers'], x['applied_date'])
            )
            # Convert to the format expected by the rest of the function
            sorted_users = [(item['user_id'], item['app']) for item in sorted_users]
            
        elif tab_type == 'youtube':
            # YouTube ranking
            sorted_apps = list(EditorApplication.objects.filter(
                channel_type='youtube',
                status='accepted',
                removal_requested=False
            ).select_related('user').order_by('-follower_count', 'applied_date'))
            sorted_users = [(app.user_id, app) for app in sorted_apps]
            
        elif tab_type == 'tiktok':
            # TikTok ranking
            sorted_apps = list(EditorApplication.objects.filter(
                channel_type='tiktok',
                status='accepted',
                removal_requested=False
            ).select_related('user').order_by('-follower_count', 'applied_date'))
            sorted_users = [(app.user_id, app) for app in sorted_apps]
        
        # Helper function to get total followers and platform info for a user (for mix ranking)
        def get_user_total_followers(user_id):
            if tab_type == 'mix':
                user_apps = EditorApplication.objects.filter(
                    user_id=user_id,
                    status='accepted',
                    removal_requested=False
                )
                return sum(app.follower_count for app in user_apps)
            return None
        
        def get_user_platforms(user_id):
            """Get list of platforms a user has (for mix ranking display)"""
            if tab_type == 'mix':
                user_apps = EditorApplication.objects.filter(
                    user_id=user_id,
                    status='accepted',
                    removal_requested=False
                )
                return [app.channel_type for app in user_apps]
            return []
        
        # Find current user's position and get users above/below
        for index, (user_id, app) in enumerate(sorted_users, start=1):
            if user_id == request.user.id:
                user_rank = index
                user_rank_app = app
                user_platforms = []
                # For mix ranking, get total followers and platforms
                if tab_type == 'mix':
                    total_followers = get_user_total_followers(user_id)
                    user_platforms = get_user_platforms(user_id)
                    # Create a modified app object with total followers for display
                    class AppWithTotalFollowers:
                        def __init__(self, app, total_followers, platforms):
                            self.user = app.user
                            self.channel_name = app.channel_name
                            self.channel_type = app.channel_type
                            self.channel_thumbnail = app.channel_thumbnail
                            self.follower_count = total_followers
                            self.platforms = platforms
                    user_rank_app = AppWithTotalFollowers(app, total_followers, user_platforms)
                else:
                    user_platforms = [app.channel_type]
                
                # Get user above (index - 1)
                if index > 1:
                    rank_above_app = sorted_users[index - 2][1]
                    above_follower_count = rank_above_app.follower_count
                    above_platforms = []
                    if tab_type == 'mix':
                        above_follower_count = get_user_total_followers(rank_above_app.user_id)
                        above_platforms = get_user_platforms(rank_above_app.user_id)
                    # Prefer the user's display picture helper (local media) over raw profile_picture URL
                    rank_above_user = rank_above_app.user
                    if hasattr(rank_above_user, 'get_display_picture'):
                        rank_above_display_picture = rank_above_user.get_display_picture()
                    else:
                        rank_above_display_picture = rank_above_user.profile_picture.url if rank_above_user.profile_picture else ''
                    rank_above = {
                        'app': rank_above_app,
                        'rank': index - 1,
                        'user': rank_above_user,
                        'channel_name': rank_above_app.channel_name or rank_above_user.username,
                        'follower_count': above_follower_count,
                        'channel_type': rank_above_app.channel_type,
                        'channel_thumbnail': rank_above_app.channel_thumbnail or '',
                        'display_picture': rank_above_display_picture,
                        'platforms': above_platforms if tab_type == 'mix' else [rank_above_app.channel_type],
                    }
                # Get user below (index + 1)
                if index < len(sorted_users):
                    rank_below_app = sorted_users[index][1]
                    below_follower_count = rank_below_app.follower_count
                    below_platforms = []
                    if tab_type == 'mix':
                        below_follower_count = get_user_total_followers(rank_below_app.user_id)
                        below_platforms = get_user_platforms(rank_below_app.user_id)
                    rank_below_user = rank_below_app.user
                    if hasattr(rank_below_user, 'get_display_picture'):
                        rank_below_display_picture = rank_below_user.get_display_picture()
                    else:
                        rank_below_display_picture = rank_below_user.profile_picture.url if rank_below_user.profile_picture else ''
                    rank_below = {
                        'app': rank_below_app,
                        'rank': index + 1,
                        'user': rank_below_user,
                        'channel_name': rank_below_app.channel_name or rank_below_user.username,
                        'follower_count': below_follower_count,
                        'channel_type': rank_below_app.channel_type,
                        'channel_thumbnail': rank_below_app.channel_thumbnail or '',
                        'display_picture': rank_below_display_picture,
                        'platforms': below_platforms if tab_type == 'mix' else [rank_below_app.channel_type],
                    }
                break
        
        return {
            'user_rank': user_rank,
            'user_rank_app': user_rank_app,
            'rank_above': rank_above,
            'rank_below': rank_below,
            'user_platforms': user_platforms if 'user_platforms' in locals() else [],
        }
    
    # Get ranking data for the selected tab
    ranking_data = get_ranking_data(ranking_tab)
    user_rank = ranking_data['user_rank']
    user_rank_app = ranking_data['user_rank_app']
    rank_above = ranking_data['rank_above']
    rank_below = ranking_data['rank_below']
    user_platforms = ranking_data.get('user_platforms', [])
    
    # Fallback: if user not found in selected tab, try mix ranking
    if user_rank is None and ranking_tab != 'mix':
        ranking_data = get_ranking_data('mix')
        user_rank = ranking_data['user_rank']
        user_rank_app = ranking_data['user_rank_app']
        rank_above = ranking_data['rank_above']
        rank_below = ranking_data['rank_below']
        user_platforms = ranking_data.get('user_platforms', [])
        ranking_tab = 'mix'  # Switch to mix if user not in selected tab
    
    # Get edit submissions platform filter (similar to ranking_tab)
    edit_platform_tab = request.GET.get('edit_platform_tab', 'mix')
    if edit_platform_tab not in ['mix', 'youtube', 'tiktok']:
        edit_platform_tab = 'mix'
    
    # Get edit submissions count
    edit_submissions = EditSubmission.objects.filter(user=request.user)
    
    # Filter by platform if not 'mix'
    if edit_platform_tab != 'mix':
        edit_submissions = edit_submissions.filter(channel_type=edit_platform_tab)
    
    total_edit_submissions = edit_submissions.count()
    verified_edit_submissions = edit_submissions.filter(status='verified').count()
    
    # Get current week submissions with stats
    from edithub.utils import get_week_start_end
    from datetime import datetime, timezone
    week_start_dt, week_end_dt = get_week_start_end()
    current_week_start = week_start_dt.date()
    current_week_end = (week_start_dt + timedelta(days=6)).date()
    
    # Get current week submissions (filtered by platform)
    current_week_submissions_qs = EditSubmission.objects.filter(
        user=request.user,
        status='verified'
    ).filter(
        Q(scheduled_week=current_week_start) |
        (Q(scheduled_week__isnull=True) & Q(submitted_date__gte=week_start_dt) & Q(submitted_date__lte=week_end_dt))
    )
    
    if edit_platform_tab != 'mix':
        current_week_submissions_qs = current_week_submissions_qs.filter(channel_type=edit_platform_tab)
    
    current_week_submissions = current_week_submissions_qs.order_by('-calculated_points', '-submitted_date')
    
    # Calculate stats (filtered by platform)
    best_points = edit_submissions.aggregate(Max('calculated_points'))['calculated_points__max'] or 0
    total_upvotes = edit_submissions.aggregate(Sum('upvote_count'))['upvote_count__sum'] or 0
    
    # Get current week rank (best edit's rank in current week for selected platform)
    current_week_rank = None
    if current_week_submissions.exists():
        # Get all verified edits for current week (same platform filter) to calculate rank
        all_current_week_edits = EditSubmission.objects.filter(
            status='verified'
        ).filter(
            Q(scheduled_week=current_week_start) |
            (Q(scheduled_week__isnull=True) & Q(submitted_date__gte=week_start_dt) & Q(submitted_date__lte=week_end_dt))
        )
        
        if edit_platform_tab != 'mix':
            all_current_week_edits = all_current_week_edits.filter(channel_type=edit_platform_tab)
        
        all_current_week_edits = all_current_week_edits.order_by('-calculated_points', 'submitted_date')
        
        # Find user's best edit and its rank
        user_best_edit = current_week_submissions.first()
        if user_best_edit:
            for index, edit in enumerate(all_current_week_edits, start=1):
                if edit.id == user_best_edit.id:
                    current_week_rank = index
                    break
    
    # Get upcoming week submissions (submissions scheduled for next week)
    next_week_start = (week_start_dt + timedelta(days=7)).date()
    deadline = datetime.combine(next_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    can_edit_delete = now < deadline
    
    upcoming_submissions = EditSubmission.objects.filter(
        user=request.user,
        scheduled_week=next_week_start
    )
    
    if edit_platform_tab != 'mix':
        upcoming_submissions = upcoming_submissions.filter(channel_type=edit_platform_tab)
    
    upcoming_submissions = upcoming_submissions.order_by('channel_type')

    # Prepare current user's image data
    current_user_image = ''
    if user_rank_app:
        # Prefer the user's display picture helper (local media) first
        rank_user = user_rank_app.user
        if hasattr(rank_user, 'get_display_picture'):
            current_user_image = rank_user.get_display_picture() or ''
        # Fallback to channel thumbnail if no display picture is available
        if not current_user_image:
            current_user_image = user_rank_app.channel_thumbnail or ''
    
    # Get display name and picture based on user's profile display mode
    display_name = request.user.get_display_name()
    display_picture = request.user.get_display_picture()
    
    # Get unread notification count
    from notifications.manager import notification_manager
    unread_notification_count = notification_manager.get_unread_count(request.user)
    
    # Get current title info from primary application
    current_title = None
    if primary_app:
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
    
    context = {
        'applications': applications,
        'total_applications': applications.count(),
        'pending_applications': applications.filter(status='pending').count(),
        'accepted_applications': applications.filter(status='accepted').count(),
        'editor_application': editor_application,
        'has_editor_application': editor_applications.exists(),
        'youtube_application': youtube_application,
        'tiktok_application': tiktok_application,
        'has_youtube_application': youtube_application is not None,
        'has_tiktok_application': tiktok_application is not None,
        'youtube_rank': youtube_rank,
        'tiktok_rank': tiktok_rank,
        'user_rank': user_rank,
        'user_rank_app': user_rank_app,
        'current_user_image': current_user_image,
        'has_rank': user_rank is not None,
        'rank_above': rank_above,
        'rank_below': rank_below,
        'ranking_tab': ranking_tab,
        'total_edit_submissions': total_edit_submissions,
        'verified_edit_submissions': verified_edit_submissions,
        'upcoming_submissions': upcoming_submissions,
        'can_edit_delete': can_edit_delete,
        'deadline': deadline,
        'next_week_start': next_week_start,
        'edit_platform_tab': edit_platform_tab,
        'current_week_submissions': current_week_submissions,
        'best_points': best_points,
        'total_upvotes': total_upvotes,
        'current_week_rank': current_week_rank,
        'display_name': display_name,
        'display_picture': display_picture,
        'current_title': current_title,
        'unread_notification_count': unread_notification_count,
        'user_platforms': user_platforms,
    }
    return render(request, 'dashboard/user_dashboard.html', context)


@login_required
def user_applications(request):
    if request.user.role != 'user':
        messages.error(request, "Access denied. User account required.")
        return redirect('home')

    applications = EventApplication.objects.filter(applicant=request.user).order_by('-applied_date')

    context = {
        'applications': applications,
        'total_applications': applications.count(),
        'pending_applications': applications.filter(status='pending').count(),
        'accepted_applications': applications.filter(status='accepted').count(),
    }
    return render(request, 'dashboard/user_applications.html', context)

@login_required
def manage_application(request, application_id):
    if request.user.role != 'admin':  # Only event hosts (admins) can manage applications
        messages.error(request, "Access denied.")
        return redirect('home')

    application = get_object_or_404(EventApplication, id=application_id, event__created_by=request.user)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(EventApplication.STATUS_CHOICES):
            application.status = new_status
            application.save()
            messages.success(request, "Application status updated successfully!")

    return redirect('dashboard:admin_dashboard')

@login_required
def edit_application(request, application_id):
    application = get_object_or_404(EventApplication, id=application_id, applicant=request.user)

    if application.status != 'pending':
        messages.error(request, "You can only edit pending applications.")
        return redirect('dashboard:user_dashboard')

    event = application.event

    if request.method == 'POST':
        form = EventApplicationForm(request.POST, event=event)
        if form.is_valid():
            # Save or update dynamic field responses
            for field in event.custom_fields.all():
                field_name = f'field_{field.id}'
                value = form.cleaned_data.get(field_name)

                response, _ = EventFieldResponse.objects.get_or_create(
                    application=application,
                    field=field
                )

                if field.field_type == 'text':
                    response.value_text = value
                elif field.field_type == 'number':
                    response.value_number = value
                elif field.field_type == 'date':
                    response.value_date = value
                elif field.field_type == 'boolean':
                    response.value_boolean = value if value else False

                response.save()

            messages.success(request, "Application updated successfully!")
            return redirect('dashboard:user_dashboard')
    else:
        # Pre-fill the form with previous answers
        initial = {}
        for response in application.field_responses.all():
            initial[f'field_{response.field.id}'] = (
                response.value_text or response.value_number or response.value_date or response.value_boolean
            )

        form = EventApplicationForm(initial=initial, event=event)

    return render(request, 'dashboard/edit_application.html', {
        'form': form,
        'event': event,
    })

@login_required
def withdraw_application(request, application_id):
    application = get_object_or_404(EventApplication, id=application_id, applicant=request.user)

    if application.status != 'pending':
        messages.error(request, "You can only withdraw pending applications.")
        return redirect('dashboard:user_dashboard')

    application.delete()
    messages.success(request, "Application withdrawn successfully!")

    return redirect('dashboard:user_dashboard')



@login_required
def application_detail(request, application_id):
    if request.user.role != 'admin':
        messages.error(request, "Access denied.")
        return redirect('home')

    application = get_object_or_404(EventApplication, id=application_id, event__created_by=request.user)
    event = application.event
    applicant = application.applicant
    custom_fields = event.custom_fields.all()

    # Collect user responses if applicable
    # (we'll keep this flexible depending on your dynamic form system)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(EventApplication.STATUS_CHOICES):
            application.status = new_status
            application.save()
            messages.success(request, "Application status updated.")
            return redirect('dashboard:admin_dashboard')

    return render(request, 'dashboard/application_detail.html', {
        'application': application,
        'event': event,
        'applicant': applicant,
        'custom_fields': custom_fields,
    })
