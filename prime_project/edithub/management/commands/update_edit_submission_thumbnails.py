"""
Management command to update channel thumbnails for EditSubmission records.
This updates the banner images in the "View All Edits" page.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from edithub.models import EditSubmission, EditorApplication
from edithub.utils import fetch_youtube_channel_data, fetch_tiktok_channel_data
import time


class Command(BaseCommand):
    help = 'Update channel thumbnails for EditSubmission records (for banner display)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            type=str,
            choices=['youtube', 'tiktok', 'all'],
            default='all',
            help='Which platform to update (default: all)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of submissions to update',
        )
        parser.add_argument(
            '--from-application',
            action='store_true',
            help='Update from related EditorApplication instead of fetching from API',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update all submissions, even if they already have thumbnails',
        )

    def handle(self, *args, **options):
        platform_filter = options['platform']
        limit = options.get('limit')
        from_application = options.get('from_application', False)
        force = options.get('force', False)

        # Build queryset
        queryset = EditSubmission.objects.filter(status='verified')
        
        if platform_filter != 'all':
            queryset = queryset.filter(channel_type=platform_filter)
        
        # Filter by missing thumbnails unless force is set
        if not force:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(channel_thumbnail__isnull=True) | Q(channel_thumbnail='')
            )
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        
        if total == 0:
            self.stdout.write(
                self.style.SUCCESS('No submissions need updating.')
            )
            return
        
        self.stdout.write(
            self.style.WARNING(f'Found {total} submission(s) to update.')
        )
        
        updated = 0
        failed = 0
        
        for submission in queryset:
            try:
                self.stdout.write(f'Processing: {submission.channel_name or submission.channel_link} ({submission.channel_type})...')
                
                new_thumbnail = ''
                
                if from_application:
                    # Try to get from approved_application first
                    if submission.approved_application:
                        app = submission.approved_application
                        if app.channel_thumbnail:
                            new_thumbnail = app.channel_thumbnail.strip()
                            # Also update channel_name if missing
                            if not submission.channel_name and app.channel_name:
                                submission.channel_name = app.channel_name
                    # If no approved_application or no thumbnail, try to find any EditorApplication for this user/channel
                    if not new_thumbnail:
                        app = EditorApplication.objects.filter(
                            user=submission.user,
                            channel_type=submission.channel_type,
                            status='accepted',
                            removal_requested=False
                        ).first()
                        if app and app.channel_thumbnail:
                            new_thumbnail = app.channel_thumbnail.strip()
                            # Also update channel_name if missing
                            if not submission.channel_name and app.channel_name:
                                submission.channel_name = app.channel_name
                else:
                    # Fetch from API (this will get fresh URLs, especially important for TikTok)
                    if submission.channel_type == 'youtube':
                        channel_data = fetch_youtube_channel_data(submission.channel_link)
                    else:  # tiktok
                        channel_data = fetch_tiktok_channel_data(submission.channel_link)
                    
                    if channel_data.get('error'):
                        self.stdout.write(
                            self.style.ERROR(f'  Error: {channel_data["error"]}')
                        )
                        failed += 1
                        continue
                    
                    new_thumbnail = (channel_data.get('thumbnail') or '').strip()
                    # Also update channel_name if missing
                    if not submission.channel_name and channel_data.get('channel_name'):
                        submission.channel_name = channel_data.get('channel_name')
                
                # Update if we got a thumbnail
                if new_thumbnail:
                    submission.channel_thumbnail = new_thumbnail
                    fields_to_update = ['channel_thumbnail']
                    if not submission.channel_name:
                        fields_to_update.append('channel_name')
                    submission.save(update_fields=fields_to_update)
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Updated thumbnail for {submission.channel_name or submission.channel_link}')
                    )
                    updated += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f'  No thumbnail found for {submission.channel_name or submission.channel_link}')
                    )
                    failed += 1
                
                # Rate limiting - be nice to APIs
                if not from_application:
                    time.sleep(1)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  Exception: {str(e)}')
                )
                failed += 1
                continue
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(f'✓ Successfully updated: {updated}')
        )
        if failed > 0:
            self.stdout.write(
                self.style.WARNING(f'✗ Failed: {failed}')
            )

