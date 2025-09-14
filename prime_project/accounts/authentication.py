from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
import logging

User = get_user_model()

logger = logging.getLogger(__name__)

class EmailBackend(BaseBackend):
    """
    Custom authentication backend that allows users to log in using their email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate a user by their email and password.
        Note: username parameter contains the email after form cleaning.
        """
        # The EmailAuthenticationForm cleans the username field and returns email
        email = username
        
        if not email or not password:
            logger.warning("Missing email or password in authentication")
            return None
            
        try:
            user = User.objects.get(email=email)
            logger.info(f"User found: {email}")

            if user.check_password(password):
                logger.info(f"Password correct for user: {email}")
                return user
            else:
                logger.warning(f"Invalid password for user: {email}")
                return None

        except User.DoesNotExist:
            logger.warning(f"User with email {email} does not exist")
            return None

    def get_user(self, user_id):
        """
        Retrieve a user by their ID.
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
