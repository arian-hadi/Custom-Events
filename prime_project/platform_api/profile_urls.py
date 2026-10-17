from django.urls import path

from . import profile_views

urlpatterns = [
    path("profile/", profile_views.profile, name="v2-member-profile"),
    path("profile/delete/", profile_views.delete_profile, name="v2-member-profile-delete"),
]
