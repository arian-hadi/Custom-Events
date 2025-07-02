# announcements/views.py

from django.shortcuts import render
from .models import Announcement
from django.shortcuts import render, get_object_or_404

def announcement_list(request):
    announcements = Announcement.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'announcements/list.html', {'announcements': announcements})


def announcement_detail(request, id):
    announcement = get_object_or_404(Announcement, id=id)
    return render(request, 'announcements/detail.html', {'announcement': announcement})