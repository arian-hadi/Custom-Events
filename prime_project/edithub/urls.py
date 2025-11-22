from django.urls import path
from . import views

app_name = 'edithub'

urlpatterns = [
    # Public views
    path('', views.RankingTableView.as_view(), name='ranking_table'),
    
    # Application views
    path('apply/', views.apply_view, name='apply'),
    path('confirm/', views.confirm_application, name='confirm_application'),
    path('application/<int:pk>/', views.application_detail, name='application_detail'),
    path('application/<int:pk>/remove/', views.request_removal, name='request_removal'),
    
    # AJAX endpoints
    path('verify-channel/', views.verify_channel_ajax, name='verify_channel'),
    path('user-stats/', views.get_user_stats_ajax, name='get_user_stats'),
    
    # Admin views
    path('admin/', views.admin_applications, name='admin_applications'),
    path('admin/application/<int:pk>/update-status/', views.admin_update_status, name='admin_update_status'),
    
    # Edit of the Week views
    path('submit-edit/', views.submit_edit, name='submit_edit'),
    path('confirm-edit/', views.confirm_edit_submission, name='confirm_edit_submission'),
    path('edits/', views.view_all_edits, name='view_all_edits'),
    path('edit/<int:pk>/upvote/', views.upvote_edit, name='upvote_edit'),
    path('edit/<int:pk>/report/', views.report_edit, name='report_edit'),
    
    # Edit of the Week admin views
    path('admin/reported-edits/', views.admin_reported_edits, name='admin_reported_edits'),
    path('admin/report/<int:pk>/resolve/', views.admin_resolve_report, name='admin_resolve_report'),
    
    # Tournament match views
    path('tournament/matches/', views.tournament_matches, name='tournament_matches'),
    path('tournament/match/<str:match_type>/', views.tournament_match_detail, name='tournament_match_detail'),
    path('tournament/match/<str:match_type>/vote/', views.vote_tournament_match, name='vote_tournament_match'),
]

