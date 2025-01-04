from django.urls import path
from .views import HomeView,HomeAPIView

urlpatterns = [
    path("", HomeView.as_view(), name = 'home'),
    path("api/", HomeAPIView.as_view(), name="home-api"),
]