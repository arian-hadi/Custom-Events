from django.urls import path
from . import campaign_views, activity_views

app_name = 'member_email'
urlpatterns = [
    path('activity/unsubscribe/<str:token>/', activity_views.unsubscribe_confirmation, name='activity_unsubscribe'),
    path('activity/one-click/<str:token>/', activity_views.one_click, name='activity_one_click'),
    path('unsubscribe/<str:token>/', campaign_views.unsubscribe_confirmation, name='unsubscribe'),
    path('one-click/<str:token>/', campaign_views.one_click, name='one_click'),
]
