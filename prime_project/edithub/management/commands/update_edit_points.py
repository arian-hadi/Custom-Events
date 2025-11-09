"""
Management command to update edit points daily.
This should be run via cron job or scheduled task daily.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Max
from datetime import timedelta
from edithub.models import EditSubmission
from edithub.utils import fetch_youtube_video_stats, fetch_tiktok_video_stats
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update points for all verified edit submissions based on platform statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if already updated today',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        
        # Get all verified edits
        edits = EditSubmission.objects.filter(status='verified')
        
        if not force:
            # Only update edits that haven't been updated today (DAILY UPDATE)
            # This ensures each edit is only updated once per day
            today = timezone.now().date()
            edits = edits.filter(
                Q(last_points_calculation__isnull=True) |
                Q(last_points_calculation__date__lt=today)
            )
        
        total = edits.count()
        updated = 0
        errors = 0
        
        self.stdout.write(f'Found {total} edits to update...')
        
        for edit in edits:
            try:
                # Fetch video statistics
                if edit.channel_type == 'youtube':
                    stats = fetch_youtube_video_stats(edit.video_url)
                    if stats.get('error'):
                        logger.warning(f"Error fetching YouTube stats for edit {edit.id}: {stats['error']}")
                        # Continue with existing stats if API fails
                        continue
                    
                    edit.views = stats.get('views', 0)
                    edit.likes = stats.get('likes', 0)
                    edit.comments = stats.get('comments', 0)
                    # OPTIMIZATION: Reuse subscriber count from EditorApplication instead of fetching again
                    # This reduces API calls by 50% - channel data is already stored when user applies
                    if edit.approved_application:
                        edit.subscriber_count = edit.approved_application.follower_count
                    else:
                        # Fallback: use API value if no approved_application exists (shouldn't happen)
                        edit.subscriber_count = stats.get('subscriber_count', 0)
                    
                elif edit.channel_type == 'tiktok':
                    stats = fetch_tiktok_video_stats(edit.video_url)
                    if stats.get('error'):
                        logger.warning(f"Error fetching TikTok stats for edit {edit.id}: {stats['error']}")
                        # Continue with existing stats if API fails
                        continue
                    
                    edit.views = stats.get('views', 0)
                    edit.likes = stats.get('likes', 0)
                    edit.comments = stats.get('comments', 0)
                    # OPTIMIZATION: Reuse follower count from EditorApplication instead of fetching again
                    # This reduces API calls by 50% - channel data is already stored when user applies
                    if edit.approved_application:
                        edit.subscriber_count = edit.approved_application.follower_count
                    else:
                        # Fallback: use API value if no approved_application exists (shouldn't happen)
                        edit.subscriber_count = stats.get('follower_count', 0)
                
                # Update upvote count
                edit.update_upvote_count()
                
                # Calculate and update points
                calculated_points = edit.calculate_points()
                edit.calculated_points = calculated_points
                edit.last_points_calculation = timezone.now()
                
                # Update weeks_participated (check if user submitted in previous week)
                # This is a simplified version - you might want to refine this logic
                user_previous_week = EditSubmission.objects.filter(
                    user=edit.user,
                    status='verified',
                    submitted_date__lt=edit.submitted_date - timedelta(days=7)
                ).aggregate(Max('submitted_date'))
                
                if user_previous_week['submitted_date__max']:
                    # User has submitted before, increment weeks
                    weeks_ago = (edit.submitted_date.date() - user_previous_week['submitted_date__max'].date()).days // 7
                    if weeks_ago <= 1:  # Within 1 week of previous submission
                        edit.weeks_participated = EditSubmission.objects.filter(
                            user=edit.user,
                            status='verified',
                            submitted_date__lte=edit.submitted_date
                        ).count()
                    else:
                        edit.weeks_participated = 1  # Reset if gap is too long
                else:
                    edit.weeks_participated = 1
                
                edit.save()
                updated += 1
                
                if updated % 10 == 0:
                    self.stdout.write(f'Updated {updated}/{total} edits...')
                    
            except Exception as e:
                logger.error(f"Error updating edit {edit.id}: {str(e)}")
                errors += 1
                continue
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated} edits. {errors} errors occurred.'
            )
        )

