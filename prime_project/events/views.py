from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Event, EventApplication
from .forms import EventForm, EventApplicationForm, EventSearchForm,EventFieldForm

def home(request):
    """Homepage showing featured events."""
    featured_events = Event.objects.filter(is_active=True)[:6]
    context = {
        'featured_events': featured_events,
    }
    return render(request, 'events/home.html', context)



@login_required
def add_event_field(request, event_id):
    """Admins can add custom fields to their events."""
    event = get_object_or_404(Event, id=event_id, created_by=request.user)

    if request.method == 'POST':
        form = EventFieldForm(request.POST)
        if form.is_valid():
            field = form.save(commit=False)
            field.event = event
            field.save()
            messages.success(request, "Field added successfully!")
            return redirect('events:add_event_field', event_id=event.id)
    else:
        form = EventFieldForm()

    fields = event.custom_fields.all()  # Show existing fields

    context = {
        'event': event,
        'form': form,
        'fields': fields,
    }
    return render(request, 'events/add_event_field.html', context)


def event_list(request):
    """List all active events with search filters."""
    form = EventSearchForm(request.GET)
    events = Event.objects.filter(is_active=True)

    if form.is_valid():
        search = form.cleaned_data.get('search')

        if search:
            events = events.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )

    paginator = Paginator(events, 9)  # 9 events per page
    page = request.GET.get('page')
    events = paginator.get_page(page)

    context = {
        'events': events,
        'form': form,
    }
    return render(request, 'events/event_list.html', context)

def event_detail(request, event_id):
    """Show event details and allow members to apply."""
    event = get_object_or_404(Event, id=event_id, is_active=True)
    application_form = EventApplicationForm() if request.user.is_authenticated else None
    has_applied = False

    if request.user.is_authenticated:
        has_applied = EventApplication.objects.filter(
            event=event, applicant=request.user  # Fixed `applicant` instead of `user`
        ).exists()

    context = {
        'event': event,
        'application_form': application_form,
        'has_applied': has_applied,
    }
    return render(request, 'events/event_detail.html', context)

@login_required
def post_event(request):
    """Admins can create new events."""
    if request.user.role != "admin":
        messages.error(request, "Only admins can create events.")
        return redirect('home')

    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            messages.success(request, "Event posted successfully! Now add custom fields.")
            return redirect('events:add_event_field', event_id=event.id)  # ✅ updated redirect
    else:
        form = EventForm()

    return render(request, 'events/post_event.html', {'form': form})


@login_required
def apply_event(request, event_id):
    """Members can apply to an event."""
    if request.user.role != "user":  # Fixed user role check
        messages.error(request, "Only members can apply for events.")
        return redirect('events:event_detail', event_id=event_id)

    event = get_object_or_404(Event, id=event_id, is_active=True)
    
    if EventApplication.objects.filter(event=event, applicant=request.user).exists():
        messages.info(request, "You have already applied for this event.")
        return redirect('events:event_detail', event_id=event_id)

    if request.method == 'POST':
        form = EventApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.event = event
            application.applicant = request.user
            application.save()
            messages.success(request, "Application submitted successfully!")
            return redirect('dashboard:user_dashboard')

    return redirect('events:event_detail', event_id=event_id)
