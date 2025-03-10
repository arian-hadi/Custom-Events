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

    # Password Reset URLs
    path('password-reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset-complete/', PasswordResetCompleteView.as_view(), name='password_reset_complete'),

]
