from django.urls import path
from . import api_views as views

app_name = 'accounts_api'
urlpatterns = [
    path('session/', views.session_view, name='session'),
    path('csrf/', views.session_view, name='csrf'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('verify-email/', views.verify_email, name='verify-email'),
    path('resend-verification/', views.resend_verification, name='resend-verification'),
    path('password-reset/', views.password_reset, name='password-reset'),
    path('password-reset-confirm/', views.password_reset_confirm, name='password-reset-confirm'),
    path('password-change/', views.password_change, name='password-change'),
    path('profile/', views.profile, name='profile'),
    path('google/start/', views.google_start, name='google-start'),
    path('google/link/', views.google_link, name='google-link'),
    path('google/callback/', views.google_callback, name='google-callback'),
]
