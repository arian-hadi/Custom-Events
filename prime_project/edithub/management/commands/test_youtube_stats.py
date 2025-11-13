"""
Test command to verify YouTube video statistics fetching and points calculation.
Run this to test if YouTube API integration is working correctly.
"""
from django.core.management.base import BaseCommand
from edithub.utils import fetch_youtube_video_stats, calculate_youtube_points
from edithub.models import EditSubmission
import time


class Command(BaseCommand):
    help = 'Test YouTube video statistics fetching and points calculation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--video-url',
            type=str,
            help='YouTube video URL to test (optional, will use first verified edit if not provided)',
        )
        parser.add_argument(
            '--duration',
            type=int,
            default=5,
            help='Duration in minutes to run the test (default: 5)',
        )

    def handle(self, *args, **options):
        video_url = options.get('video_url')
        duration_minutes = options.get('duration', 5)
        duration_seconds = duration_minutes * 60
        
        self.stdout.write(self.style.SUCCESS(f'Starting YouTube stats test for {duration_minutes} minutes...'))
        self.stdout.write('=' * 60)
        
        # Get a test video URL
        if not video_url:
            # Try to get a verified YouTube edit from database
            youtube_edit = EditSubmission.objects.filter(
                status='verified',
                channel_type='youtube'
            ).first()
            
            if youtube_edit:
                video_url = youtube_edit.video_url
                self.stdout.write(f'Using video from database: {video_url}')
            else:
                self.stdout.write(self.style.ERROR('No YouTube edits found in database.'))
                self.stdout.write('Please provide a --video-url or add a YouTube edit first.')
                return
        
        self.stdout.write(f'Testing URL: {video_url}')
        self.stdout.write('=' * 60)
        
        start_time = time.time()
        iteration = 0
        
        while time.time() - start_time < duration_seconds:
            iteration += 1
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            
            self.stdout.write(f'\n[{minutes:02d}:{seconds:02d}] Iteration {iteration}')
            self.stdout.write('-' * 60)
            
            # Fetch stats
            self.stdout.write('Fetching YouTube video statistics...')
            stats = fetch_youtube_video_stats(video_url)
            
            if stats.get('error'):
                self.stdout.write(self.style.ERROR(f'❌ Error: {stats["error"]}'))
            else:
                views = stats.get('views', 0)
                likes = stats.get('likes', 0)
                comments = stats.get('comments', 0)
                subscriber_count = stats.get('subscriber_count', 0)
                
                self.stdout.write(self.style.SUCCESS('✅ Stats fetched successfully:'))
                self.stdout.write(f'   Views: {views:,}')
                self.stdout.write(f'   Likes: {likes:,}')
                self.stdout.write(f'   Comments: {comments:,}')
                self.stdout.write(f'   Subscribers: {subscriber_count:,}')
                
                # Calculate points
                if subscriber_count > 0:
                    points = calculate_youtube_points(views, likes, comments, subscriber_count)
                    self.stdout.write(f'\n📊 Calculated Points: {points:.2f}')
                    
                    # Show breakdown
                    normalized_views = views / subscriber_count
                    normalized_likes = likes / subscriber_count
                    normalized_comments = comments / subscriber_count
                    engagement_rate = ((likes + comments) / views * 100) if views > 0 else 0
                    
                    self.stdout.write('\n   Breakdown:')
                    self.stdout.write(f'   - Normalized Views: {normalized_views:.4f}')
                    self.stdout.write(f'   - Normalized Likes: {normalized_likes:.4f}')
                    self.stdout.write(f'   - Normalized Comments: {normalized_comments:.4f}')
                    self.stdout.write(f'   - Engagement Rate: {engagement_rate:.2f}%')
                    self.stdout.write(f'\n   Formula:')
                    self.stdout.write(f'   ({normalized_views:.4f} × 0.4) + ({normalized_likes:.4f} × 0.3) + ({normalized_comments:.4f} × 0.2) + ({engagement_rate:.2f} × 0.1) = {points:.2f}')
                else:
                    self.stdout.write(self.style.WARNING('⚠️  No subscriber count, cannot calculate points'))
            
            # Wait before next iteration (30 seconds)
            if time.time() - start_time < duration_seconds - 30:
                self.stdout.write('\n⏳ Waiting 30 seconds before next test...')
                time.sleep(30)
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'✅ Test completed after {duration_minutes} minutes'))
        self.stdout.write(f'Total iterations: {iteration}')

