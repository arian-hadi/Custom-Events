from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
import json
from .models import Notification, NotificationPreference
from .manager import notification_manager


@login_required
def notification_list(request):
    """Get list of notifications for the current user"""
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    # Get unread count
    unread_count = notification_manager.get_unread_count(request.user)
    
    # Pagination (optional - can be added later)
    # For now, return all notifications
    
    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'notification_type': notification.notification_type,
            'is_read': notification.is_read,
            'created_at': notification.created_at.isoformat(),
            'related_object_type': notification.related_object_type,
            'related_object_id': notification.related_object_id,
        })
    
    return JsonResponse({
        'success': True,
        'notifications': notifications_data,
        'unread_count': unread_count,
    })


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a specific notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.mark_as_read()
    
    return JsonResponse({
        'success': True,
        'message': 'Notification marked as read'
    })


@login_required
@require_http_methods(["POST"])
def mark_all_read(request):
    """Mark all notifications as read for the current user"""
    count = notification_manager.mark_all_as_read(request.user)
    
    return JsonResponse({
        'success': True,
        'message': f'{count} notifications marked as read',
        'count': count
    })


@login_required
@require_http_methods(["POST"])
def delete_notification(request, notification_id):
    """Delete a specific notification"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.delete()
    
    return JsonResponse({
        'success': True,
        'message': 'Notification deleted'
    })


@login_required
def get_unread_count(request):
    """Get unread notification count"""
    count = notification_manager.get_unread_count(request.user)
    
    return JsonResponse({
        'success': True,
        'unread_count': count
    })
