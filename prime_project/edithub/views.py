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
from .models import EditorApplication
from .forms import EditorApplicationForm
from .utils import fetch_youtube_channel_data, fetch_tiktok_channel_data, validate_channel_url
from accounts.models import CustomUser
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
        
        # Filter by editing area if provided
        editing_area = self.request.GET.get('editing_area')
        if editing_area:
            base_queryset = base_queryset.filter(
                Q(editing_area=editing_area) | Q(editing_area='all')
            )
        self.selected_area = editing_area or ''

        channel_filter = self.request.GET.get('channel_filter', 'mix').lower()
        if channel_filter not in ['mix', 'youtube', 'tiktok']:
            channel_filter = 'mix'

        self.channel_counts = {
            'mix': base_queryset.values('user_id').distinct().count(),
            'youtube': base_queryset.filter(channel_type='youtube').count(),
            'tiktok': base_queryset.filter(channel_type='tiktok').count(),
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
        context['channel_counts'] = getattr(self, 'channel_counts', {
            'mix': 0,
            'youtube': 0,
            'tiktok': 0,
        })
        channel_filter = context['channel_filter']
        show_all = self.request.GET.get('all') == '1'
        context['show_all'] = show_all
        context['search_query'] = getattr(self, 'search_query', '') if hasattr(self, 'search_query') else self.request.GET.get('q', '')

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
            queryset = getattr(self, 'full_queryset', super().get_queryset())
            # current user rank (platform)
            current_user_rank = None
            if self.request.user.is_authenticated:
                ids = list(queryset.values_list('user_id', flat=True))
                try:
                    idx = ids.index(self.request.user.id)
                    current_user_rank = idx + 1
                except ValueError:
                    current_user_rank = None
            context['current_user_rank'] = current_user_rank

            if show_all:
                paginator = Paginator(queryset, self.paginate_by)
                page_number = self.request.GET.get('page')
                page_obj = paginator.get_page(page_number)
                context['rankings'] = page_obj.object_list
                context['object_list'] = page_obj.object_list
                context['page_obj'] = page_obj
                context['is_paginated'] = page_obj.has_other_pages()
                context['paginator'] = paginator
            else:
                top5 = list(queryset[:5])
                context['rankings'] = top5
                context['object_list'] = top5
                context['is_paginated'] = False
            context['total_editors'] = queryset.count()
        
        return context

    def _build_mix_entries(self):
        mix_queryset = getattr(self, 'mix_queryset', EditorApplication.objects.none())
        applications = list(mix_queryset)
        grouped = defaultdict(list)

        for application in applications:
            grouped[application.user_id].append(application)

        entries = []
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
            display_user_name = apps[0].user.get_full_name() or apps[0].user.username
            display_thumbnail = primary_app.channel_thumbnail if primary_app else ''
            entries.append({
                'user': apps[0].user,
                'apps': apps,
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

        entries.sort(
            key=lambda entry: (
                -(entry['total_followers'] or 0),
                entry['primary'].applied_date if entry['primary'] else None
            )
        )

        for index, entry in enumerate(entries, start=1):
            entry['rank'] = index

        return entries


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
        return render(request, 'edithub/apply.html', {
            'youtube_form': youtube_form,
            'tiktok_form': tiktok_form,
            'apply_youtube': apply_youtube,
            'apply_tiktok': apply_tiktok,
            'data_consent_checked': data_consent_checked,
            'existing_applications': user_applications,
            'existing_applications_grouped': grouped_existing,
        })

    if request.method == 'POST':
        apply_youtube = request.POST.get('apply_youtube') == 'on'
        apply_tiktok = request.POST.get('apply_tiktok') == 'on'
        data_consent = request.POST.get('data_consent') == 'on'

        if not (apply_youtube or apply_tiktok):
            messages.error(request, "Select at least one platform to apply for.")
            youtube_form = build_form('youtube', 'youtube')
            tiktok_form = build_form('tiktok', 'tiktok')
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        if not data_consent:
            messages.error(request, "You must consent to data usage to proceed.")
            youtube_form = build_form('youtube', 'youtube')
            tiktok_form = build_form('tiktok', 'tiktok')
            return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        def prepare_form(prefix, channel_type, enabled):
            if not enabled:
                return build_form(prefix, channel_type)
            post_data = request.POST.copy()
            post_data[f'{prefix}-channel_type'] = channel_type
            post_data[f'{prefix}-data_consent'] = 'on'
            return build_form(prefix, channel_type, data=post_data, files=request.FILES)

        youtube_form = prepare_form('youtube', 'youtube', apply_youtube)
        tiktok_form = prepare_form('tiktok', 'tiktok', apply_tiktok)

        forms_to_process = []
        if apply_youtube:
            if youtube_form.is_valid():
                forms_to_process.append(('youtube', youtube_form))
            else:
                logger.warning("YouTube form validation failed: %s", youtube_form.errors)
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        if apply_tiktok:
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
            duplicate_link = EditorApplication.objects.filter(
                user=request.user,
                channel_link=channel_link
            ).exclude(status='rejected')
            if duplicate_link.exists():
                messages.error(request, "You have already submitted this channel link.")
                return render_apply_form(youtube_form, tiktok_form, apply_youtube, apply_tiktok, data_consent)

        created_applications = []

        try:
            for platform, form in forms_to_process:
                channel_link = form.cleaned_data['channel_link'].strip()

                if platform == 'youtube':
                    channel_data = fetch_youtube_channel_data(channel_link)
                else:
                    channel_data = fetch_tiktok_channel_data(channel_link)

                if channel_data.get('error'):
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

    return render_apply_form(youtube_form, tiktok_form, apply_youtube=True, apply_tiktok=False, data_consent_checked=False)


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
    
    messages.success(request, f"Application status updated to {application.get_status_display()}")
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': new_status})
    
    return redirect('edithub:admin_applications')
