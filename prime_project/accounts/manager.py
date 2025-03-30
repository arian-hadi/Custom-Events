from django.contrib.auth.models import BaseUserManager
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    """Custom manager for the CustomUser model that uses email as the primary identifier."""

    def email_validator(self, email):
        """Validate email format."""
        try:
            validate_email(email)
        except ValidationError:
            raise ValueError(_("Please enter a valid email address"))

    def create_user(self, email, display_username, password=None, **extra_fields):
        """Create and return a regular user with email and username."""
        if not email:
            raise ValueError(_("An email address is required"))
        if not display_username:
            raise ValueError(_("A username is required"))

        email = self.normalize_email(email)
        self.email_validator(email)

        user = self.model(email=email, display_username=display_username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, display_username, password=None, **extra_fields):
        """Create and return a superuser with admin privileges."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True"))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True"))

        return self.create_user(email, display_username, password, **extra_fields)
