from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now
from datetime import timedelta
from .manager import UserManager

# Custom User Model
class CustomUser(AbstractUser):
    # Remove first_name and last_name by overriding them
    first_name = None
    last_name = None

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('user', 'User'),
    )

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)  
    role = models.CharField(choices=ROLE_CHOICES, default='user', max_length=10)
    is_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Only 'username' will be required

    objects = UserManager()

    def __str__(self):
        return self.email
    
    def is_member(self):
        return self.role == 'member'
    
    def is_admin(self):
        return self.role == 'admin'

# One-Time Password Model
class OneTimePassword(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=now)

    class Meta:
        # At most one active code per user; allow different users to share the same 6-digit code.
        unique_together = ('user', 'code')
        indexes = [
            models.Index(fields=['user', 'code']),
            models.Index(fields=['created_at']),
    ]

    def is_expired(self):
        return self.created_at < now() - timedelta(minutes=10)

    def __str__(self):
        return f"{self.user.username} passcode"


        


