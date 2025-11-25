from django.core.management.base import BaseCommand
from edithub.models import EditorApplication
from edithub.utils import download_image_from_url
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Set user profile pictures from their accepted EditorApplication channel thumbnails'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Process only a specific user ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options.get('user_id')
        
        # Find all accepted applications where user doesn't have a profile picture
        queryset = EditorApplication.objects.filter(
            status='accepted',
            channel_thumbnail__isnull=False
        ).exclude(
            channel_thumbnail=''
        ).select_related('user')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        else:
            # Only get applications where user doesn't have profile picture
            queryset = queryset.filter(user__profile_picture__isnull=True)
        
        total = queryset.count()
        if total == 0:
            self.stdout.write(
                self.style.WARNING('No users found that need profile pictures set.')
            )
            return
        
        self.stdout.write(f'Found {total} user(s) to process...')
        
        updated = 0
        failed = 0
        skipped = 0
        
        for app in queryset:
            user = app.user
            channel_thumbnail = app.channel_thumbnail
            
            # Double-check user doesn't have profile picture (in case of race condition)
            if user.profile_picture:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Skipping user {user.username} (ID: {user.id}) - already has profile picture'
                    )
                )
                skipped += 1
                continue
            
            self.stdout.write(
                f'  Processing user {user.username} (ID: {user.id}) - {app.channel_type} application'
            )
            self.stdout.write(f'    Channel thumbnail: {channel_thumbnail}')
            
            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS('    [DRY RUN] Would download and set profile picture')
                )
                updated += 1
                continue
            
            try:
                # Download image from URL
                downloaded_image = download_image_from_url(channel_thumbnail)
                
                if downloaded_image:
                    # Set user's profile picture
                    user.profile_picture = downloaded_image
                    user.save(update_fields=['profile_picture'])
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'    ✓ Successfully set profile picture for {user.username}'
                        )
                    )
                    updated += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'    ✗ Failed to download image from {channel_thumbnail}'
                        )
                    )
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Error setting profile picture for user {user.id}: {e}")
                self.stdout.write(
                    self.style.ERROR(
                        f'    ✗ Error: {str(e)}'
                    )
                )
                failed += 1
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN - Would update: {updated}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated: {updated}'))
            if skipped > 0:
                self.stdout.write(self.style.WARNING(f'Skipped (already have picture): {skipped}'))
            if failed > 0:
                self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

