from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *
from .forms import CustomPasswordResetForm

urlpatterns = [
    # path('signup/', SignUpView.as_view(), name='signup'),
    # path('login/', EmailLoginView.as_view() , name='login'),
    # path('logout/',LogoutView.as_view(), name="logout"),
    # path('password_reset/', auth_views.PasswordResetView.as_view(template_name='accounts/password_reset_form.html',form_class=CustomPasswordResetForm), name='password_reset'),
    # path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    # path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    # path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
    # path('check_session/',checkSessionView.as_view(), name = "check-session" ),
    # path('api/token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    # path('api/token/refresh/', MyTokenRefreshView.as_view(), name='token_refresh'),
    # path('register/', RegisterView.as_view(), name='register'),
    path('register/', RegisterUserView.as_view(), name = 'register'),
    path('verify-email/', VerifyUserEmail.as_view(), name = "verify-email"),
    path('login/',LoginUserView.as_view(), name = 'Login'),
    path('profile/', TestingAuthenticatedView.as_view(), name = "granted"),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset-confirm/<uidb64>/<token>/', PasswordResetConfirm.as_view(), name='password-reset-confirm'),
    path('set-new-password/', SetNewPasswordView.as_view(), name='set-new-password'),
    path('logout/', LogoutApiView.as_view(), name='logout')
]
