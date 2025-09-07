from django.db import models

def upload_to(instance, filename):
    return f'announcements/{filename}'

class Announcement(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    thumbnail = models.ImageField(upload_to=upload_to, null=True, blank=True)
    image = models.ImageField(upload_to=upload_to, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

