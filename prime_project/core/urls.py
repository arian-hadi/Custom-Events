from django.urls import path
from .views import HomeView, TermOfServiceView, PrivacyPolicyView, AboutView, DisclaimersView

urlpatterns = [
    path("", HomeView.as_view(), name = 'home'),
    path('terms/', TermOfServiceView.as_view(), name='terms'),
    path('privacy/', PrivacyPolicyView.as_view(), name='privacy'),
    path('about/', AboutView.as_view(), name='about'),
    path('disclaimers/', DisclaimersView.as_view(), name='disclaimers'),

]