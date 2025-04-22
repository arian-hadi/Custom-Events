from django.urls import path
from .views import HomeView, TermOfServiceView, PrivacyPolicyView

urlpatterns = [
    path("", HomeView.as_view(), name = 'home'),
    path('terms/', TermOfServiceView.as_view(), name='terms'),
    path('privacy/', PrivacyPolicyView.as_view(), name='privacy'),

]