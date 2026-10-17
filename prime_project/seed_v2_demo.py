"""Populate the isolated Docker V2 preview with clearly marked visual fixtures.

Usage inside the development backend:
    python seed_v2_demo.py --assets /tmp/v2-demo-assets

Rerunning refreshes only these named demo records and the demo member password.
No real users/applications are approved and no email is sent or queued.
"""
import argparse
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prime_project.settings')

import django
django.setup()

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from events.models import Event, EventApplication, EventField, EventFieldResponse
from notifications.models import MemberEmailCampaign, Notification, NotificationPreference
from platform_api.models import BlogPost
from shop.models import Product


ASSETS = {
    'stickers': '57618ce4cd-62c821bad16f950f25562d93_more-image-sticker-p-500.jpeg',
    'studio': 'e7e88c185e-62c44a18b9509efb74cf2d97_05-blog-post-1920-p-800.jpeg',
    'creative': 'd85c80713f-62c442ec334299911e91de30_01-blog-post-1920-p-800.jpeg',
    'community': '93994a012b-62c4458bd99e488ca985a7cf_02-blog-post-1920-p-800.jpeg',
    'lighting': 'ef204e830b-62c446ebb057d3fa73c49407_03-blog-post-1920-p-800.jpeg',
    'setup': '3d5f2c43fd-62c448fd9017e45970ce75fa_04-blog-post-1920-p-800.jpeg',
    'collection': '1d98841a37-62c44e27265ab552523c26e7_06-blog-post-1920-p-800.jpeg',
}
MEMBER_EMAIL = 'demo-member@example.test'
ORGANIZER_EMAIL = 'demo-curator@example.test'
NOTICE = '<p><strong>Demo content:</strong> A fictional example for local website previews.</p>'


def assert_local():
    db = settings.DATABASES['default']
    if not (settings.DEBUG and db['NAME'] == 'platform_v2' and db['HOST'] == 'db'
            and settings.V2_FRONTEND_URL == 'http://localhost:8082'
            and not settings.ENABLE_EDITHUB_SCHEDULER):
        raise RuntimeError('This script only supports the isolated local platform_v2 Docker database.')


def suppress_publication_email(kind, obj):
    # A cancelled source marker prevents automatic discovery in other running
    # workers, even if campaigns are enabled later. Commit with the publication.
    campaign, _ = MemberEmailCampaign.objects.get_or_create(
        source_key=f'{kind}:{obj.pk}', defaults={
            'topic': 'blog_updates' if kind == 'blog' else 'shop_updates',
            'subject': f'[DEMO - DO NOT SEND] {getattr(obj, "title", getattr(obj, "name", ""))}'[:180],
            'body': 'Local visual fixture. Automatic email intentionally suppressed.',
            'status': 'cancelled',
        },
    )
    if campaign.status != 'cancelled':
        raise RuntimeError('An existing campaign uses this demo source; no changes committed.')


def seed(asset_dir):
    assert_local()
    for filename in ASSETS.values():
        if not (asset_dir / filename).is_file():
            raise RuntimeError(f'Missing existing site artwork: {filename}')
    images = {}
    for key, filename in ASSETS.items():
        destination = f'demo-v2/{key}.jpeg'
        if not default_storage.exists(destination):
            default_storage.save(destination, ContentFile((asset_dir / filename).read_bytes()))
        images[key] = destination

    now = timezone.now()
    password = 'Demo-Cybertron-' + secrets.token_hex(5)
    with transaction.atomic():
        organizer, created = CustomUser.objects.get_or_create(email=ORGANIZER_EMAIL, defaults={
            'username': 'DemoCommunityTeam', 'role': 'admin', 'is_active': False,
        })
        if (organizer.username != 'DemoCommunityTeam' or organizer.is_active
                or organizer.is_staff or organizer.is_superuser or organizer.role != 'admin'):
            raise RuntimeError('Demo curator identity is already in use; no data changed.')
        if created:
            organizer.set_unusable_password()
            organizer.save(update_fields=['password'])
        member, _ = CustomUser.objects.get_or_create(email=MEMBER_EMAIL, defaults={
            'username': 'DemoCreator', 'role': 'user', 'is_verified': True,
        })
        if member.username != 'DemoCreator' or member.is_staff or member.is_superuser or member.role != 'user':
            raise RuntimeError('Demo member identity is already in use; no data changed.')
        member.is_active = member.is_verified = True
        member.set_password(password)
        member.save(update_fields=['password', 'is_active', 'is_verified'])
        NotificationPreference.objects.update_or_create(user=member, defaults={
            'email_enabled': False, 'email_newsletter': False,
            'email_blog_updates': False, 'email_shop_updates': False,
        })

        product_specs = [
            ('Creator Sticker Collection', 'stickers', '12.00', '8.00', False, False),
            ('Cybertron Color Presets', 'creative', '24.00', '16.00', False, False),
            ('Autobot Wallpaper Collection', 'lighting', '9.00', None, True, False),
            ('Energon Transition Pack', 'community', '19.00', None, False, False),
            ('Cinematic Sound Design Guide', 'studio', '15.00', '11.00', False, False),
            ('Community Poster Collection', 'collection', '18.00', None, False, False),
            ('Collector Display Stand', 'setup', '32.00', '25.00', False, True),
            ('Studio Lighting Kit', 'lighting', '59.00', None, False, True),
        ]
        products = []
        for index, (name, image, price, sale, free, external) in enumerate(product_specs):
            product, _ = Product.objects.update_or_create(name=f'{name} [Demo]', defaults={
                'description': NOTICE + '<p>An example listing showing how product photography, pricing and details look in the store.</p>'
                    '<h3>Preview details</h3><ul><li>Illustrative artwork from the supplied website assets</li>'
                    '<li>Sample pricing and description</li><li>No real purchase or download is available</li></ul>',
                'category': 'merges_1_0' if external else 'transformers_2_0',
                'thumbnail': images[image], 'main_image': images[image],
                'image_2': images['studio'] if index == 0 else None,
                'original_price': Decimal(price),
                'discounted_price': Decimal(sale) if sale else None,
                'discount_active': bool(sale), 'free_deadline_active': free,
                'free_deadline': now + timedelta(days=7) if free else None,
                'redirect_url': 'https://example.com/?preview=transformers-demo',
                'ecommerce_platform': 'other' if external else 'none',
                'is_active': True,
            })
            Product.objects.filter(pk=product.pk).update(created_at=now - timedelta(days=index))
            suppress_publication_email('shop', product)
            products.append(product)
        for product in products[:3]:
            product.favorites.add(member)

        post_specs = [
            ('Building a cinematic Transformers edit', 'cinematic-edit', 'Editing tutorials', 'creative',
             'Plan your story, find the strongest moments and give every cut a purpose.'),
            ('Inside a creator\'s workspace', 'creator-workspace', 'Creator life', 'studio',
             'A look at lighting, comfort and the small habits that make editing sessions easier.'),
            ('Five ways to make your transitions feel intentional', 'intentional-transitions', 'Editing tutorials', 'lighting',
             'Use movement, rhythm and continuity to connect your shots.'),
            ('Community spotlight: the people behind the edits', 'community-spotlight', 'Community', 'community',
             'Meet a fictional group of creators sharing ideas and helping each other improve.'),
            ('Designing a display for your collection', 'collection-display', 'Collecting', 'collection',
             'A sample feature about spacing, lighting and telling a story with your display.'),
            ('Preparing your work for a community showcase', 'showcase-checklist', 'Community', 'setup',
             'A simple preparation checklist covering titles, credits, exports and presentation.'),
        ]
        posts = []
        for index, (title, slug, category, image, excerpt) in enumerate(post_specs):
            post, _ = BlogPost.objects.update_or_create(slug='demo-' + slug, defaults={
                'title': title + ' [Demo]', 'excerpt': excerpt,
                'category': category, 'cover_image': images[image], 'author': organizer,
                'status': 'published', 'published_at': now - timedelta(days=index + 1),
                'body': NOTICE + f'<p>{excerpt}</p><h2>Start with a clear idea</h2>'
                    '<p>Choose one feeling or story you want the viewer to remember. Build a short sequence around that idea before adding effects.</p>'
                    '<h2>Make the details count</h2><p>Watch the rhythm, contrast and pacing. Leave room for the strongest moments and check the final result on a smaller screen.</p>'
                    '<h2>Share and learn</h2><p>Ask the community for specific feedback and keep a note of what you want to improve in your next project.</p>',
            })
            suppress_publication_email('blog', post)
            posts.append(post)

        event_specs = [
            ('Autobot Community Showcase', 7, 12, 'Share a short Transformers-inspired edit and explain the idea behind it.'),
            ('Cinematic Editing Workshop', 10, 16, 'Explore pacing, sound design and matching movement between shots.'),
            ('Creator Collaboration Night', 14, 21, 'Meet other creators and plan a small collaborative project.'),
            ('Collector Photography Challenge', 21, 28, 'Build a scene with your collection and share your favorite photograph.'),
            ('Previous Community Screening', -10, -3, 'A completed sample event showing the closed application state.'),
        ]
        events = []
        for index, (title, deadline_days, event_days, description) in enumerate(event_specs):
            event, _ = Event.objects.update_or_create(title=title + ' [Demo]', created_by=organizer, defaults={
                'description': NOTICE + '<p>' + description + '</p>',
                'details': '<h3>What to expect</h3><ul><li>Community feedback and friendly discussion</li>'
                    '<li>A chance to share your creative process</li><li>No real event registration, fee or prize</li></ul>',
                'deadline': now + timedelta(days=deadline_days), 'date': now + timedelta(days=event_days),
                'is_active': True,
            })
            fields = []
            for label, field_type in [('Your portfolio or project idea', 'text'), ('How many edits have you made?', 'number'), ('Happy to share feedback?', 'boolean')]:
                field, _ = EventField.objects.get_or_create(event=event, name=label, defaults={'field_type': field_type})
                fields.append(field)
            if index < 3:
                application, _ = EventApplication.objects.update_or_create(event=event, applicant=member, defaults={
                    'status': 'accepted', 'cover_letter': 'Demo application: I would love to share my work and learn from other creators.',
                })
                for field, values in zip(fields, [{'value_text': 'A fictional cinematic Optimus Prime edit.'}, {'value_number': 12}, {'value_boolean': True}]):
                    EventFieldResponse.objects.update_or_create(application=application, field=field, defaults=values)
                Notification.objects.get_or_create(user=member, title=f'Approved: {title} [Demo]', defaults={
                    'message': 'Your demo event application has been accepted. Open Applications to see the details.',
                    'notification_type': 'application_approved', 'related_object_type': 'EventApplication',
                    'related_object_id': application.pk, 'is_read': index == 2,
                })
            events.append(event)

    return {
        'products': len(products), 'published_posts': len(posts), 'events': len(events),
        'approved_applications': 3, 'favorites': 3, 'notifications': 3,
        'member_email': MEMBER_EMAIL, 'member_password': password,
        'product_ids': [item.pk for item in products], 'blog_slugs': [item.slug for item in posts],
        'event_ids': [item.pk for item in events],
        'real_email_sent': False, 'original_records_modified': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(seed(arguments.assets)))
