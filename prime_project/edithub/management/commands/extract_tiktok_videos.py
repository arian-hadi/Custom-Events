"""
Management command to extract direct video URLs for existing TikTok videos.
This retroactively processes videos that were submitted before the extraction feature was added.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from edithub.models import EditSubmission
from edithub.utils import extract_tiktok_video_url
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Extract direct video URLs for existing TikTok videos that don\'t have direct_video_url set'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-extract even if direct_video_url already exists',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of videos to process',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        limit = options.get('limit')
        
        # Get TikTok videos that need extraction
        queryset = EditSubmission.objects.filter(
            channel_type='tiktok',
            status='verified'
        )
        
        if not force:
            queryset = queryset.filter(
                direct_video_url__isnull=True
            )
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        self.stdout.write(f'Found {total} TikTok videos to process...')
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No videos to process.'))
            return
        
        updated = 0
        errors = 0
        
        for edit in queryset:
            try:
                self.stdout.write(f'Processing video {edit.id}: {edit.video_url[:50]}...')
                
                # Extract video URL (with timeout protection)
                self.stdout.write('  ⏳ Extracting video URL (this may take 10-30 seconds)...')
                try:
                    video_data = extract_tiktok_video_url(edit.video_url)
                except KeyboardInterrupt:
                    self.stdout.write(self.style.ERROR('  ❌ Interrupted by user'))
                    raise
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ❌ Unexpected error: {str(e)}'))
                    video_data = {'error': str(e)}
                
                if video_data.get('video_url') and not video_data.get('error'):
                    edit.direct_video_url = video_data['video_url']
                    edit.save(update_fields=['direct_video_url'])
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Extracted video URL'))
                else:
                    error_msg = video_data.get('error', 'Unknown error')
                    self.stdout.write(self.style.WARNING(f'  ⚠️  Failed: {error_msg}'))
                    errors += 1
                    logger.warning(f"Failed to extract video URL for edit {edit.id}: {error_msg}")
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Error: {str(e)}'))
                logger.error(f"Error processing edit {edit.id}: {str(e)}")
                errors += 1
                continue
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'✅ Successfully extracted {updated} video URLs. {errors} errors occurred.'
        ))
        
        if updated > 0:
            self.stdout.write(self.style.SUCCESS(
                '🎉 Videos will now display as clean HTML5 players instead of TikTok embeds!'
            ))

