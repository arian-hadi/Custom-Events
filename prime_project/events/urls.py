from django.urls import path
from . import views

from django.urls import path
from . import views

app_name = 'events'  # Namespace for event URLs

urlpatterns = [
    path('events/', views.event_list, name='event_list'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/apply/', views.apply_event, name='apply_event'),
    path('create/', views.event_info_step, name='event_info_step'),   
    path('add-fields/', views.add_event_fields, name='add_event_fields'),  
    path('finish/', views.finish_event_creation, name='finish_event_creation'), 
    path('events/<int:event_id>/delete/', views.delete_event, name='delete_event'),
]
