from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from edithub.utils import check_user_achievements
from edithub.models import EditorApplication

User = get_user_model()


class Command(BaseCommand):
    help = 'Check and unlock achievements for all users (or a specific user)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Check achievements for a specific user by username',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Check achievements for all users with accepted applications',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        check_all = options.get('all', False)
        
        if username:
            try:
                user = User.objects.get(username=username)
                self.check_user_achievements(user)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User "{username}" not found.'))
        elif check_all:
            # Get all users with accepted applications
            accepted_apps = EditorApplication.objects.filter(status='accepted', removal_requested=False)
            users = User.objects.filter(editor_applications__in=accepted_apps).distinct()
            
            self.stdout.write(f'Checking achievements for {users.count()} users...')
            for user in users:
                self.check_user_achievements(user)
        else:
            self.stdout.write(self.style.ERROR(
                'Please specify --username <username> or --all to check achievements.'
            ))

    def check_user_achievements(self, user):
        """Check achievements for a single user"""
        unlocked = check_user_achievements(user)
        if unlocked:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ {user.username}: Unlocked {len(unlocked)} title(s): {", ".join([t.name for t in unlocked])}'
                )
            )
        else:
            self.stdout.write(f'  {user.username}: No new titles unlocked')

