from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *
from .views import (
    RegisterUserView, VerifyUserEmail, EmailLoginView, CustomLogoutView,
    CustomPasswordResetView, CustomPasswordResetConfirmView
)

from django.contrib.auth.views import PasswordResetDoneView, PasswordResetCompleteView

urlpatterns = [
    # #JWT
    # path('register/', RegisterUserView.as_view(), name = 'register'),
    # path('verify-email/', VerifyUserEmail.as_view(), name = "verify-email"),
    # path('login/',LoginUserView.as_view(), name = 'Login'),
    # path('profile/', TestingAuthenticatedView.as_view(), name = "granted"),
    # path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    # path('password-reset-confirm/<uidb64>/<token>/', PasswordResetConfirm.as_view(), name='password-reset-confirm'),
    # path('set-new-password/', SetNewPasswordView.as_view(), name='set-new-password'),
    # path('logout/', LogoutApiView.as_view(), name='logout')
    path('signup/', RegisterUserView.as_view(), name='signup'),
    path('verify-email/', VerifyUserEmail.as_view(), name='verify_email'),
    path('login/', EmailLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend_otp'),
    path('create-superuser/', create_superuser_temp),
    path("debug-admin/", debug_admin_user),




    # Password Reset URLs
    path('password-reset/', CustomPasswordResetView.as_view(template_name="registration/password_reset_form.html"), name='password_reset'),
    path('password-reset/done/', PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"), name='password_reset_confirm'),
    path('password-reset-complete/', PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"), name='password_reset_complete'),

]
