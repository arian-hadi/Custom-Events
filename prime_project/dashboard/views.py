from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from events.models import Event, EventApplication  # Use the correct models
from django.contrib.auth import get_user_model

User = get_user_model()

def home(request):
    return render(request, 'dashboard/home.html')

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':  # Check role-based access
        messages.error(request, "Access denied. Admin account required.")
        return redirect('home')

    hosted_events = Event.objects.filter(host=request.user)
    recent_applications = EventApplication.objects.filter(event__host=request.user).order_by('-applied_date')[:5]

    context = {
        'hosted_events': hosted_events,
        'recent_applications': recent_applications,
        'total_events': hosted_events.count(),
        'total_applications': EventApplication.objects.filter(event__host=request.user).count(),
    }
    return render(request, 'dashboard/admin_dashboard.html', context)

@login_required
def user_dashboard(request):
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
    return render(request, 'dashboard/user_dashboard.html', context)

@login_required
def manage_application(request, application_id):
    if request.user.role != 'admin':  # Only event hosts (admins) can manage applications
        messages.error(request, "Access denied.")
        return redirect('home')

    application = get_object_or_404(EventApplication, id=application_id, event__host=request.user)

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
        return redirect('dashboard/user_dashboard')

    if request.method == 'POST':
        application.save()
        messages.success(request, "Application updated successfully!")
        return redirect('dashboard:user_dashboard')

    return redirect('dashboard:user_dashboard')

@login_required
def withdraw_application(request, application_id):
    application = get_object_or_404(EventApplication, id=application_id, applicant=request.user)

    if application.status != 'pending':
        messages.error(request, "You can only withdraw pending applications.")
        return redirect('dashboard:user_dashboard')

    application.delete()
    messages.success(request, "Application withdrawn successfully!")

    return redirect('dashboard:user_dashboard')
