from django.core.management.base import BaseCommand
from edithub.models import EditorTitle


class Command(BaseCommand):
    help = 'Create default editor titles with different rarity tiers'

    def handle(self, *args, **options):
        titles_data = [
            # Comment titles (auto-assigned based on channel type)
            {'name': 'YouTube Editor', 'rarity': 'ordinary', 'category': 'comment', 'description': 'Default title for YouTube editors', 'cost_coins': 0, 'is_default': True},
            {'name': 'TikTok Editor', 'rarity': 'ordinary', 'category': 'comment', 'description': 'Default title for TikTok editors', 'cost_coins': 0, 'is_default': True},
            
            # Reel titles - Ordinary
            {'name': 'Video Editor', 'rarity': 'ordinary', 'category': 'reel', 'description': 'A creative video editor', 'cost_coins': 0},
            {'name': 'Content Creator', 'rarity': 'ordinary', 'category': 'reel', 'description': 'Creates amazing content', 'cost_coins': 0},
            {'name': 'Reel Master', 'rarity': 'ordinary', 'category': 'reel', 'description': 'Master of reel editing', 'cost_coins': 0},
            
            # Reel titles - Epic
            {'name': 'Master Editor', 'rarity': 'epic', 'category': 'reel', 'description': 'A master of the editing craft', 'cost_coins': 100},
            {'name': 'Creative Genius', 'rarity': 'epic', 'category': 'reel', 'description': 'Unleash your creative genius', 'cost_coins': 150},
            {'name': 'Edit Wizard', 'rarity': 'epic', 'category': 'reel', 'description': 'Magical editing skills', 'cost_coins': 200},
            {'name': 'Visual Storyteller', 'rarity': 'epic', 'category': 'reel', 'description': 'Tells stories through visuals', 'cost_coins': 180},
            {'name': 'Transition Master', 'rarity': 'epic', 'category': 'reel', 'description': 'Master of smooth transitions', 'cost_coins': 120},
            {'name': 'Reel Legend', 'rarity': 'epic', 'category': 'reel', 'description': 'A legend in reel editing', 'cost_coins': 250},
            
            # Reel titles - Legendary
            {'name': 'Ultimate Editing Master', 'rarity': 'legendary', 'category': 'reel', 'description': 'The ultimate master of editing', 'cost_coins': 500},
            {'name': 'Legendary Editor', 'rarity': 'legendary', 'category': 'reel', 'description': 'A legendary editing legend', 'cost_coins': 600},
            {'name': 'Edit of the Gods', 'rarity': 'legendary', 'category': 'reel', 'description': 'Divine editing skills', 'cost_coins': 750},
            {'name': 'The Editing Prodigy', 'rarity': 'legendary', 'category': 'reel', 'description': 'A prodigy in the editing world', 'cost_coins': 650},
            {'name': 'Supreme Editor', 'rarity': 'legendary', 'category': 'reel', 'description': 'Supreme editing excellence', 'cost_coins': 700},
            
            # General titles - Ordinary
            {'name': 'Editor', 'rarity': 'ordinary', 'category': 'general', 'description': 'A skilled editor', 'cost_coins': 0},
            {'name': 'Content Maker', 'rarity': 'ordinary', 'category': 'general', 'description': 'Creates engaging content', 'cost_coins': 0},
            
            # General titles - Epic
            {'name': 'Creative Master', 'rarity': 'epic', 'category': 'general', 'description': 'Master of creativity', 'cost_coins': 150},
            {'name': 'Visual Artist', 'rarity': 'epic', 'category': 'general', 'description': 'An artist of visuals', 'cost_coins': 200},
            
            # General titles - Legendary
            {'name': 'Editing Legend', 'rarity': 'legendary', 'category': 'general', 'description': 'A true editing legend', 'cost_coins': 600},
        ]
        
        created_count = 0
        updated_count = 0
        
        for title_data in titles_data:
            title, created = EditorTitle.objects.update_or_create(
                name=title_data['name'],
                defaults={
                    'rarity': title_data['rarity'],
                    'category': title_data.get('category', 'general'),
                    'description': title_data['description'],
                    'cost_coins': title_data['cost_coins'],
                    'is_default': title_data.get('is_default', False),
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created title: {title.name} ({title.get_rarity_display()})'))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'Updated title: {title.name} ({title.get_rarity_display()})'))
        
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully processed {len(titles_data)} titles:'))
        self.stdout.write(self.style.SUCCESS(f'  - Created: {created_count}'))
        self.stdout.write(self.style.SUCCESS(f'  - Updated: {updated_count}'))

