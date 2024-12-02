from django.urls import path
from django.contrib.auth import views as auth_views
from .views import SignUpView, EmailLoginView,checkSessionView 
from .forms import CustomPasswordResetForm

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', EmailLoginView.as_view() , name='login'),
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='accounts/password_reset_form.html',form_class=CustomPasswordResetForm), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
    path('check_session/',checkSessionView.as_view(), name = "check-session" )
]
