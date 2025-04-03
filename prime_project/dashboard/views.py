from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from events.models import Event, EventApplication,EventFieldResponse
from django.contrib.auth import get_user_model
from events.forms import EventApplicationForm
from django.db.models import Case, When, Value, IntegerField



User = get_user_model()

def home(request):
    return render(request, 'dashboard/home.html')

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        messages.error(request, "Access denied.")
        return redirect('home')

    hosted_events = Event.objects.filter(created_by=request.user).order_by('-posted_date')

    status_ordering = Case(
        When(status='accepted', then=Value(0)),
        When(status='pending', then=Value(1)),
        When(status='rejected', then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )

    # Apply filter from dropdown
    selected_status = request.GET.get('status')
    application_qs = EventApplication.objects.filter(event__created_by=request.user)

    if selected_status:
        application_qs = application_qs.filter(status=selected_status)

    recent_applications = application_qs.annotate(
        status_order=status_ordering
    ).order_by('status_order', '-applied_date')

    context = {
        'hosted_events': hosted_events,
        'recent_applications': recent_applications,
        'total_events': hosted_events.count(),
        'total_applications': application_qs.count(),
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
