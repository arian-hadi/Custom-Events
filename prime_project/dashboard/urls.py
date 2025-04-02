from django.urls import path
from . import views

app_name = 'dashboard' 

urlpatterns = [
    path('', views.home, name='dashboard-home'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('user/', views.user_dashboard, name='user_dashboard'),
    path('application/<int:application_id>/edit/', views.edit_application, name='edit_application'),
    path('application/<int:application_id>/manage/', views.manage_application, name='manage_event_application'),
    path('application/<int:application_id>/withdraw/', views.withdraw_application, name='withdraw_application'),
    path('application/<int:application_id>/', views.application_detail, name='application_detail'),

]
