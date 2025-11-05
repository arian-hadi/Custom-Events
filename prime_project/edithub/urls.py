from django.urls import path
from . import views

app_name = 'edithub'

urlpatterns = [
    # Public views
    path('', views.RankingTableView.as_view(), name='ranking_table'),
    
    # Application views
    path('apply/', views.apply_view, name='apply'),
    path('confirm/', views.confirm_application, name='confirm_application'),
    path('application/<int:pk>/', views.application_detail, name='application_detail'),
    path('application/<int:pk>/remove/', views.request_removal, name='request_removal'),
    
    # AJAX endpoints
    path('verify-channel/', views.verify_channel_ajax, name='verify_channel'),
    
    # Admin views
    path('admin/', views.admin_applications, name='admin_applications'),
    path('admin/application/<int:pk>/update-status/', views.admin_update_status, name='admin_update_status'),
]

