"""
Quick test script to check notification duplicates.
Run this in Django shell: python manage.py shell < test_notification_duplicates.py
Or copy-paste into Django shell.
"""
from django.utils import timezone
from notifications.models import Notification
from accounts.models import CustomUser
from datetime import timedelta

# Get today's start time
today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
today = timezone.now().date()

print("=" * 60)
print("NOTIFICATION DUPLICATE CHECK")
print("=" * 60)
print(f"\nToday's date: {today}")
print(f"Today's start time: {today_start}")

# Check all daily report notifications sent today
daily_notifications_today = Notification.objects.filter(
    notification_type='edit_of_week_daily',
    created_at__gte=today_start
).order_by('created_at')

print(f"\n📊 Daily Report Notifications Sent Today: {daily_notifications_today.count()}")

if daily_notifications_today.count() > 0:
    print("\nBreakdown by user:")
    user_counts = {}
    for notif in daily_notifications_today:
        username = notif.user.username
        if username not in user_counts:
            user_counts[username] = []
        user_counts[username].append(notif.created_at)
    
    for username, timestamps in user_counts.items():
        print(f"  • {username}: {len(timestamps)} notification(s)")
        for i, ts in enumerate(timestamps, 1):
            print(f"    {i}. Sent at {ts.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check for duplicates (same user, same day)
    duplicates = {user: count for user, count in user_counts.items() if count > 1}
    if duplicates:
        print(f"\n⚠️  DUPLICATES FOUND:")
        for user, timestamps in duplicates.items():
            print(f"  • {user}: {len(timestamps)} notifications today (should be 1)")
    else:
        print(f"\n✅ No duplicates found - each user received exactly 1 notification today")
else:
    print("\n✅ No daily report notifications sent today yet")

# Check your specific user (replace with your username)
your_username = input("\nEnter your username to check your notifications (or press Enter to skip): ").strip()
if your_username:
    try:
        user = CustomUser.objects.get(username=your_username)
        user_notifications = Notification.objects.filter(
            user=user,
            notification_type='edit_of_week_daily',
            created_at__gte=today_start
        ).order_by('created_at')
        
        print(f"\n📧 Your Daily Report Notifications Today: {user_notifications.count()}")
        for i, notif in enumerate(user_notifications, 1):
            print(f"  {i}. Created at {notif.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"     Title: {notif.title}")
    except CustomUser.DoesNotExist:
        print(f"❌ User '{your_username}' not found")

print("\n" + "=" * 60)

