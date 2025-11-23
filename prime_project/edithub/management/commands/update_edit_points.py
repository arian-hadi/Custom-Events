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
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of edits to update (useful for testing)',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        limit = options.get('limit')
        
        # Get current date to filter by scheduled_week
        today = timezone.now().date()
        
        # Get all verified edits where the scheduled week has started
        # Points should only be calculated for edits in weeks that have already begun
        edits = EditSubmission.objects.filter(
            status='verified',
            scheduled_week__lte=today  # Only edits for weeks that have started
        )
        
        if not force:
            # Only update edits that haven't been updated today (DAILY UPDATE)
            # This ensures each edit is only updated once per day
            edits = edits.filter(
                Q(last_points_calculation__isnull=True) |
                Q(last_points_calculation__date__lt=today)
            )
        
        # Apply limit if specified
        if limit:
            edits = edits[:limit]
        
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
        
        # Send daily reports to users with active edits
        self._send_daily_reports()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated} edits. {errors} errors occurred.'
            )
        )
    
    def _send_daily_reports(self):
        """Send daily Edit of the Week reports to users"""
        from notifications.manager import notification_manager
        from django.db.models import Q, Max
        from datetime import timedelta
        
        today = timezone.now().date()
        
        # Get all users who have verified edits in the current week
        # Get edits from current week (Monday to Sunday)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Get all verified edits for current week
        current_week_edits = EditSubmission.objects.filter(
            status='verified',
            scheduled_week__gte=week_start,
            scheduled_week__lte=week_end
        ).select_related('user').order_by('user', '-calculated_points')
        
        # Group by user and get their best edit
        users_with_edits = {}
        for edit in current_week_edits:
            if edit.user_id not in users_with_edits:
                users_with_edits[edit.user_id] = {
                    'user': edit.user,
                    'best_edit': edit,
                    'total_edits': 0,
                    'total_points': 0,
                    'current_rank': None
                }
            
            users_with_edits[edit.user_id]['total_edits'] += 1
            users_with_edits[edit.user_id]['total_points'] += (edit.calculated_points or 0)
        
        # Calculate current ranks for the week (based on best edit points per user)
        user_best_points = {}
        for edit in current_week_edits:
            if edit.user_id not in user_best_points:
                user_best_points[edit.user_id] = edit.calculated_points or 0
            else:
                user_best_points[edit.user_id] = max(
                    user_best_points[edit.user_id], 
                    edit.calculated_points or 0
                )
        
        # Sort users by best points
        sorted_users = sorted(
            user_best_points.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        # Assign ranks
        rank = 1
        for user_id, best_points in sorted_users:
            if user_id in users_with_edits:
                users_with_edits[user_id]['current_rank'] = rank
                rank += 1
        
        # Send notifications
        for user_data in users_with_edits.values():
            user = user_data['user']
            best_edit = user_data['best_edit']
            total_edits = user_data['total_edits']
            total_points = user_data['total_points']
            current_rank = user_data['current_rank']
            
            # Build message
            rank_text = f"#{current_rank}" if current_rank else "Not ranked yet"
            message = (
                f"📊 Daily Edit of the Week Update:\n\n"
                f"Current Standing: {rank_text}\n"
                f"Total Points: {total_points:.2f}\n"
                f"Active Edits: {total_edits}\n"
                f"Best Edit Points: {best_edit.calculated_points or 0:.2f}\n\n"
                f"Keep creating amazing content! 🎬"
            )
            
            notification_manager.create_notification(
                user=user,
                title="Edit of the Week - Daily Report",
                message=message,
                notification_type='edit_of_week_daily',
                related_object=best_edit
            )

