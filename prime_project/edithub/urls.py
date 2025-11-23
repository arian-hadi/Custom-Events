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
    
    # Profile customization
    path('customize-profile/', views.customize_profile, name='customize_profile'),
    
    # AJAX endpoints
    path('verify-channel/', views.verify_channel_ajax, name='verify_channel'),
    path('user-stats/', views.get_user_stats_ajax, name='get_user_stats'),
    path('titles/', views.get_available_titles, name='get_available_titles'),
    path('select-title/', views.select_editor_title, name='select_editor_title'),
    
    # Admin views
    path('admin/', views.admin_applications, name='admin_applications'),
    path('admin/application/<int:pk>/update-status/', views.admin_update_status, name='admin_update_status'),
    
    # Edit of the Week views
    path('submit-edit/', views.submit_edit, name='submit_edit'),
    path('edit-submission/<int:pk>/edit/', views.edit_submission, name='edit_submission'),
    path('edit-submission/<int:pk>/delete/', views.delete_submission, name='delete_submission'),
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

