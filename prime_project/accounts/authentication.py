from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
import logging

User = get_user_model()

logger = logging.getLogger(__name__)

class EmailBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(email=username)
            logger.info(f"Found user with email: {username}")
            
            if user.check_password(password):
                logger.info(f"Password check successful for user: {username}")
                return user
            else:
                logger.warning(f"Password check failed for user: {username}")
                return None
                
        except User.DoesNotExist:
            logger.warning(f"No user found with email: {username}")
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

