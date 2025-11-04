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
        queryset = EditorApplication.objects.filter(
            status='accepted',
            removal_requested=False
        ).select_related('user').order_by('-follower_count', 'applied_date')
        
        # Filter by editing area if provided
        editing_area = self.request.GET.get('editing_area')
        if editing_area:
            queryset = queryset.filter(
                Q(editing_area=editing_area) | Q(editing_area='all')
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['editing_areas'] = EditorApplication.EDITING_AREA_CHOICES
        context['selected_area'] = self.request.GET.get('editing_area', '')
        
        # Calculate statistics
        total_editors = self.get_queryset().count()
        context['total_editors'] = total_editors
        
        return context


@login_required
def apply_view(request):
    """View for submitting editor applications"""
    if request.user.role != 'user':
        messages.error(request, "Only regular users can apply to the EditingHub.")
        return redirect('home')
    
    # Check if user already has a pending or accepted application
    existing_app = EditorApplication.objects.filter(
        user=request.user,
        status__in=['pending', 'accepted']
    ).first()
    
    if existing_app and request.method != 'POST':
        messages.info(request, f"You already have a {existing_app.get_status_display().lower()} application.")
        return redirect('edithub:application_detail', pk=existing_app.pk)
    
    if request.method == 'POST':
        form = EditorApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Fetch channel data first
                channel_link = form.cleaned_data['channel_link'].strip()
                channel_type = form.cleaned_data.get('channel_type')

                logger.info(
                    "Initial channel_type detected for %s: %s",
                    request.user.username,
                    channel_type
                )

                if channel_type not in ['youtube', 'tiktok']:
                    logger.warning(
                        "channel_type not set by form (%s). Revalidating URL %s",
                        channel_type,
                        channel_link
                    )
                    is_valid, detected_type, error_message = validate_channel_url(channel_link)
                    if not is_valid:
                        messages.error(request, error_message or 'Invalid channel URL')
                        return render(request, 'edithub/apply.html', {'form': form})
                    channel_type = detected_type
                    logger.info("Revalidated channel_type: %s", channel_type)
                
                # Check if user already has an application with this channel
                existing = EditorApplication.objects.filter(
                    user=request.user,
                    channel_link=channel_link
                ).exclude(status='rejected')  # Allow re-applying if previously rejected
                
                if existing.exists():
                    messages.error(request, 'You have already applied with this channel link')
                    return render(request, 'edithub/apply.html', {'form': form})
                
                logger.info(f"Processing application for user {request.user.username}, channel: {channel_link}")
                
                if channel_type == 'youtube':
                    channel_data = fetch_youtube_channel_data(channel_link)
                else:  # tiktok
                    channel_data = fetch_tiktok_channel_data(channel_link)
                
                if channel_data.get('error'):
                    logger.warning(f"Channel data fetch error: {channel_data['error']}")
                    messages.error(request, f"Failed to fetch channel data: {channel_data['error']}")
                    return render(request, 'edithub/apply.html', {'form': form})
                
                # Store form data in session for confirmation page
                # Note: We can't store files in session, so we'll create a temporary application
                # Create application with pending_verification status
                application = EditorApplication(
                    user=request.user,
                    channel_link=channel_link,
                    channel_type=channel_type,
                    editing_area=form.cleaned_data['editing_area'],
                    editing_area_other=form.cleaned_data.get('editing_area_other', ''),
                    channel_name=channel_data.get('channel_name', ''),
                    follower_count=channel_data.get('subscriber_count') or channel_data.get('follower_count', 0),
                    channel_thumbnail=channel_data.get('thumbnail', ''),
                    channel_screenshot=form.cleaned_data['channel_screenshot'],
                    channel_verified=False,  # Will be set on confirmation
                    data_consent=True,  # Already validated
                    status='pending'  # Will be submitted after confirmation
                )
                application.save()
                logger.info(f"Application {application.pk} created successfully")
                
                # Store application ID in session for confirmation
                request.session['pending_application_id'] = application.pk
                request.session.save()  # Ensure session is saved
                
                # Redirect to confirmation page
                return redirect('edithub:confirm_application')
            except Exception as e:
                logger.error(f"Error processing application: {str(e)}", exc_info=True)
                messages.error(request, f"An error occurred: {str(e)}")
                return render(request, 'edithub/apply.html', {'form': form})
        else:
            # Form is invalid, show errors
            logger.warning(f"Form validation failed: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return render(request, 'edithub/apply.html', {'form': form})
    else:
        form = EditorApplicationForm()
    
    return render(request, 'edithub/apply.html', {'form': form})


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
    
    # Get application from session
    application_id = request.session.get('pending_application_id')
    if not application_id:
        messages.error(request, "No application data found. Please start over.")
        return redirect('edithub:apply')
    
    try:
        application = EditorApplication.objects.get(pk=application_id, user=request.user)
    except EditorApplication.DoesNotExist:
        messages.error(request, "Application not found. Please start over.")
        request.session.pop('pending_application_id', None)
        return redirect('edithub:apply')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirm':
            # User confirmed, mark as verified and keep status as pending
            application.channel_verified = True
            application.save()
            
            # Clear session
            request.session.pop('pending_application_id', None)
            
            messages.success(request, "Application submitted successfully! It will be reviewed by an admin.")
            return redirect('edithub:application_detail', pk=application.pk)
        else:
            # User cancelled, delete the application
            application.delete()
            request.session.pop('pending_application_id', None)
            messages.info(request, "Application cancelled. You can modify and resubmit.")
            return redirect('edithub:apply')
    
    # Prepare context data for display
    application_data = {
        'channel_link': application.channel_link,
        'channel_type': application.channel_type,
        'editing_area': application.editing_area,
        'editing_area_other': application.editing_area_other,
        'channel_name': application.channel_name,
        'follower_count': application.follower_count,
        'channel_thumbnail': application.channel_thumbnail,
    }
    
    context = {
        'application_data': application_data,
        'application': application,
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
    
    applications = EditorApplication.objects.all().select_related('user').order_by('-applied_date')
    
    if status_filter != 'all':
        applications = applications.filter(status=status_filter)
    
    if search_query:
        applications = applications.filter(
            Q(user__username__icontains=search_query) |
            Q(channel_name__icontains=search_query) |
            Q(channel_link__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(applications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'applications': page_obj,
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
