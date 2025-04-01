from django.urls import path
from . import views

from django.urls import path
from . import views

app_name = 'events'  # Namespace for event URLs

urlpatterns = [
    #path('', views.home, name='home'),
    path('events/', views.event_list, name='event_list'),
    # path('post/', views.post_event, name='create_event'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/apply/', views.apply_event, name='apply_event'),
    #path('events/<int:event_id>/add-fields/', views.add_event_field, name='add_event_field'),
    path('create/', views.event_info_step, name='event_info_step'),  # Step 1
    path('add-fields/', views.add_event_fields, name='add_event_fields'),  # Step 2
    path('finish/', views.finish_event_creation, name='finish_event_creation'),  # Finalize

]
