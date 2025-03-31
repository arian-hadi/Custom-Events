from django.urls import path
from . import views

from django.urls import path
from . import views

app_name = 'events'  # Namespace for event URLs

urlpatterns = [
    path('', views.home, name='home'),
    path('events/', views.event_list, name='event_list'),
    path('post/', views.post_event, name='create_event'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/apply/', views.apply_event, name='apply_event'),
]
