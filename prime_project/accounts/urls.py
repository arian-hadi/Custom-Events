from django.urls import path
from django.contrib.auth import views as auth_views
from .views import SignUpView, EmailLoginView,checkSessionView 

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', EmailLoginView.as_view() , name='login'),
    path('check_session/',checkSessionView.as_view(), name = "check-session" )
]
