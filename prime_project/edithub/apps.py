from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class EdithubConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'edithub'
    
    def ready(self):
        """Start the scheduler when Django is ready"""
        import os
        import sys
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from django.core.management import call_command
        
        # Skip if running management commands (migrate, collectstatic, test, etc.)
        if len(sys.argv) > 1 and sys.argv[1] in ['migrate', 'makemigrations', 'collectstatic', 'test', 'shell', 'dbshell']:
            return
        
        # Skip if running in test mode
        if 'test' in sys.argv or 'pytest' in sys.argv[0]:
            return
        
        def update_edit_points():
            """Function to call the management command"""
            try:
                logger.info("🔄 Starting automatic daily edit points update...")
                call_command('update_edit_points', verbosity=0)
                logger.info("✅ Daily edit points update completed successfully")
            except Exception as e:
                logger.error(f"❌ Error in automatic edit points update: {str(e)}")
        
        # Create scheduler
        scheduler = BackgroundScheduler()
        
        # Schedule the update to run every 24 hours (daily)
        # Run immediately on startup, then every 24 hours
        scheduler.add_job(
            update_edit_points,
            trigger=IntervalTrigger(hours=24),
            id='update_edit_points_daily',
            name='Update Edit Points Daily',
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
            coalesce=True,  # Combine multiple pending runs into one
            misfire_grace_time=3600  # Allow 1 hour grace period if missed
        )
        
        try:
            scheduler.start()
            logger.info("✅ Edit points scheduler started - will run every 24 hours automatically")
            # Run immediately on first startup
            update_edit_points()
        except Exception as e:
            logger.error(f"❌ Failed to start edit points scheduler: {str(e)}")
