"""
Reusable validators for file uploads
"""
from django.core.exceptions import ValidationError
from django.conf import settings


# Maximum file size constants (in MB)
MAX_IMAGE_FILE_SIZE_MB = 4  # For shop images
MAX_CHANNEL_SCREENSHOT_SIZE_MB = 10  # For channel application screenshots (matches nginx limit)


def validate_image_file_size(image, max_size_mb=MAX_IMAGE_FILE_SIZE_MB):
    """
    Validator for image file size.
    
    Args:
        image: The uploaded image file
        max_size_mb: Maximum file size in MB (default: 4MB)
    
    Raises:
        ValidationError: If file size exceeds the limit
    """
    if not image:
        return
    
    limit = max_size_mb * 1024 * 1024  # Convert MB to bytes
    if image.size > limit:
        raise ValidationError(
            f"Image file too large. Maximum size is {max_size_mb} MB. "
            f"Your file is {image.size / (1024 * 1024):.2f} MB."
        )


def validate_file_size(file, max_size_mb):
    """
    Generic validator for any file size.
    
    Args:
        file: The uploaded file
        max_size_mb: Maximum file size in MB
    
    Raises:
        ValidationError: If file size exceeds the limit
    """
    if not file:
        return
    
    limit = max_size_mb * 1024 * 1024  # Convert MB to bytes
    if file.size > limit:
        file_size_mb = file.size / (1024 * 1024)
        raise ValidationError(
            f"File too large. Maximum size is {max_size_mb} MB. "
            f"Your file is {file_size_mb:.2f} MB."
        )

