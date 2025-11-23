from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('unread-count/', views.get_unread_count, name='unread_count'),
    path('<int:notification_id>/read/', views.mark_notification_read, name='mark_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('<int:notification_id>/delete/', views.delete_notification, name='delete_notification'),
]

