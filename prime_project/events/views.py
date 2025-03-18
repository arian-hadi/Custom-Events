from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Event, EventApplication
from .forms import EventForm, EventApplicationForm, EventSearchForm

def home(request):
    """Homepage showing featured events."""
    featured_events = Event.objects.filter(is_active=True)[:6]
    context = {
        'featured_events': featured_events,
    }
    return render(request, 'events/home.html', context)

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
            event=event, user=request.user
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
    if not request.user.is_staff:  # Use Django's built-in is_staff
        messages.error(request, "Only admins can create events.")
        return redirect('home')

    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save()
            messages.success(request, "Event posted successfully!")
            return redirect('events:event_detail', event_id=event.id)
    else:
        form = EventForm()

    return render(request, 'events/post_event.html', {'form': form})


@login_required
def apply_event(request, event_id):
    """Members can apply to an event."""
    if not request.user.groups.filter(name='Members').exists():  # Check if user is in 'Members' group
        messages.error(request, "Only members can apply for events.")
        return redirect('events:event_detail', event_id=event_id)

    event = get_object_or_404(Event, id=event_id, is_active=True)
    
    if EventApplication.objects.filter(event=event, user=request.user).exists():
        messages.info(request, "You have already applied for this event.")
        return redirect('events:event_detail', event_id=event_id)

    if request.method == 'POST':
        EventApplication.objects.create(event=event, user=request.user)
        messages.success(request, "Application submitted successfully!")
        return redirect('dashboard:member_dashboard')

    return redirect('events:event_detail', event_id=event_id)
