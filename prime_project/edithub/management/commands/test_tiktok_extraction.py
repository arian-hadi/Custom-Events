"""
Test command to verify TikTok video extraction works properly.
This helps debug and verify that we can extract raw video URLs without TikTok UI.
"""
from django.core.management.base import BaseCommand
from edithub.utils import extract_tiktok_video_url
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test TikTok video extraction with a sample URL'

    def add_arguments(self, parser):
        parser.add_argument(
            'url',
            type=str,
            help='TikTok video URL to test',
        )

    def handle(self, *args, **options):
        video_url = options['url']
        
        self.stdout.write(f'Testing TikTok video extraction...')
        self.stdout.write(f'URL: {video_url}')
        self.stdout.write('')
        
        self.stdout.write('⏳ Extracting video URL (this may take 15-30 seconds)...')
        
        try:
            result = extract_tiktok_video_url(video_url)
            
            self.stdout.write('')
            if result.get('video_url'):
                self.stdout.write(self.style.SUCCESS('✅ SUCCESS! Video URL extracted:'))
                self.stdout.write(f'   {result["video_url"][:100]}...')
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('✅ This video will display as clean HTML5 player (no TikTok UI)'))
            elif result.get('error'):
                self.stdout.write(self.style.ERROR(f'❌ FAILED: {result["error"]}'))
                self.stdout.write('')
                self.stdout.write('This video will use TikTok embed fallback (with white background)')
            else:
                self.stdout.write(self.style.WARNING('⚠️  No video URL found, but no error reported'))
                
            if result.get('username'):
                self.stdout.write(f'Username: @{result["username"]}')
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR('\n❌ Interrupted by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Unexpected error: {str(e)}'))
            logger.exception("Error in test extraction")

