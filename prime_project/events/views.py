from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Event, EventApplication, EventField, EventFieldResponse
from .forms import EventForm, EventApplicationForm, EventSearchForm,EventFieldForm
from datetime import datetime
from django.views.decorators.http import require_POST
from django.utils import timezone


@login_required
def event_info_step(request):
    if request.user.role != "admin":
        messages.error(request, "Only admins can create events.")
        return redirect('home')

    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            event = Event.objects.create(
                title=data['title'],
                description=data['description'],
                details=data['details'],
                deadline=data['deadline'],
                date=data['date'],
                created_by=request.user,
                is_active=False  # Make it public only after finishing
            )
            request.session['created_event_id'] = event.id
            return redirect('events:add_event_fields')
    else:
        form = EventForm()

    return render(request, 'events/post_event.html', {'form': form})



@login_required
def add_event_fields(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect('home')

    event_id = request.session.get('created_event_id')
    if not event_id:
        messages.error(request, "Please fill out event details first.")
        return redirect('events:event_info_step')

    event = get_object_or_404(Event, id=event_id, created_by=request.user)

    if request.method == 'POST':
        form = EventFieldForm(request.POST)
        if form.is_valid():
            field = form.save(commit=False)
            field.event = event
            field.save()
            messages.success(request, "Field added successfully!")
            return redirect('events:add_event_fields')
    else:
        form = EventFieldForm()

    fields = event.custom_fields.all()

    return render(request, 'events/add_event_field.html', {
        'form': form,
        'event': event,
        'fields': fields
    })



@login_required
def finish_event_creation(request):
    event_id = request.session.get('created_event_id')

    if event_id:
        event = get_object_or_404(Event, id=event_id, created_by=request.user)
        event.is_active = True  # ✅ Make event public now
        event.save()

    # Clear session data
    request.session.pop('event_data', None)
    request.session.pop('created_event_id', None)

    messages.success(request, "Event created and published successfully!")
    return redirect('dashboard:admin_dashboard')

# @login_required
# def add_event_field(request, event_id):
#     """Admins can add custom fields to their events."""
#     event = get_object_or_404(Event, id=event_id, created_by=request.user)

#     if request.method == 'POST':
#         form = EventFieldForm(request.POST)
#         if form.is_valid():
#             field = form.save(commit=False)
#             field.event = event
#             field.save()
#             messages.success(request, "Field added successfully!")
#             return redirect('events:add_event_field', event_id=event.id)
#     else:
#         form = EventFieldForm()

#     fields = event.custom_fields.all()  # Show existing fields

#     context = {
#         'event': event,
#         'form': form,
#         'fields': fields,
#     }
#     return render(request, 'events/add_event_field.html', context)


from django.db.models import Q

def event_list(request):
    form = EventSearchForm(request.GET)
    events = Event.objects.filter(is_active=True)

    if form.is_valid():
        search = form.cleaned_data.get('search')
        admin_username = request.GET.get('location')  # Using 'location' field for admin filter

        if search:
            events = events.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )

        if admin_username:
            events = events.filter(created_by__username__icontains=admin_username)

    paginator = Paginator(events, 9)
    page = request.GET.get('page')
    events = paginator.get_page(page)

    return render(request, 'events/event_list.html', {
        'events': events,
        'form': form
    })


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id, is_active=True)
    application_form = EventApplicationForm(event=event) if request.user.is_authenticated else None
    has_applied = False
    deadline_passed = timezone.now() > event.deadline

    if request.user.is_authenticated:
        has_applied = EventApplication.objects.filter(event=event, applicant=request.user).exists()

    return render(request, 'events/event_detail.html', {
        'event': event,
        'application_form': application_form,
        'has_applied': has_applied,
        'deadline_passed': deadline_passed,
    })

# @login_required
# def post_event(request):
#     """Admins can create new events."""
#     if request.user.role != "admin":
#         messages.error(request, "Only admins can create events.")
#         return redirect('home')

#     if request.method == 'POST':
#         form = EventForm(request.POST)
#         if form.is_valid():
#             event = form.save(commit=False)
#             event.created_by = request.user
#             event.save()
#             messages.success(request, "Event posted successfully! Now add custom fields.")
#             return redirect('events:add_event_field', event_id=event.id)  # ✅ updated redirect
#     else:
#         form = EventForm()

#     return render(request, 'events/post_event.html', {'form': form})



@login_required
def apply_event(request, event_id):
    if request.user.role != "user":
        messages.error(request, "Only members can apply for events.")
        return redirect('events:event_detail', event_id=event_id)

    event = get_object_or_404(Event, id=event_id, is_active=True)

    if timezone.now() > event.deadline:
        messages.error(request, "The deadline for this event has passed. You can no longer apply.")
        return redirect('events:event_detail', event_id=event_id)



    if EventApplication.objects.filter(event=event, applicant=request.user).exists():
        messages.info(request, "You have already applied for this event.")
        return redirect('events:event_detail', event_id=event_id)

    if request.method == 'POST':
        form = EventApplicationForm(request.POST, event=event)
        if form.is_valid():
            application = form.save(commit=False)
            application.event = event
            application.applicant = request.user
            application.save()
            for field in event.custom_fields.all():
                field_name = f'field_{field.id}'
                if field_name in form.cleaned_data:
                    value = form.cleaned_data[field_name]

                    response = EventFieldResponse(application=application, field=field)

                    if field.field_type == 'text':
                        response.value_text = value
                    elif field.field_type == 'number':
                        response.value_number = value
                    elif field.field_type == 'date':
                        response.value_date = value
                    elif field.field_type == 'boolean':
                        response.value_boolean = value if value else False

                    response.save()
            messages.success(request, "Application submitted successfully!")
            return redirect('dashboard:user_dashboard')
        
    else:
        form = EventApplicationForm(event=event)
    
    

    return render(request, 'events/apply_event.html', {
        'form': form,
        'event': event,
    })


@login_required
@require_POST
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.created_by != request.user:
        messages.error(request, "You are not allowed to delete this event.")
        return redirect('events:event_detail', event_id=event_id)

    event.delete()
    messages.success(request, "Event deleted successfully.")
    return redirect('dashboard:admin_dashboard')
