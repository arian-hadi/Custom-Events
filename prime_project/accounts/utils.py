import random 
from django.core.mail import EmailMessage
from .models import CustomUser,OneTimePassword
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
import requests
import logging

logger = logging.getLogger(__name__)


def generateOtp():
    otp = ""
    for _ in range(6):
        otp += str(random.randint(1,9))
    return otp

def send_code_to_user(email, request=None):
    """
    Send OTP verification code to user's email.
    Includes a verification link for easy recovery.
    """
    subject = "One-Time Passcode for Email Verification"
    otp_code = generateOtp()

    try:
        user = CustomUser.objects.get(email=email)
    except CustomUser.DoesNotExist:
        raise ValueError("User with this email does not exist")

    # Delete any old OTPs before creating a new one
    OneTimePassword.objects.filter(user=user).delete()

    OneTimePassword.objects.create(user=user, code=otp_code)

    # Build verification link
    from django.urls import reverse
    if request:
        # Use request to build absolute URL (best method)
        verification_url = request.build_absolute_uri(reverse('continue_verification'))
    else:
        # Fallback: construct URL manually
        try:
            from django.contrib.sites.models import Site
            current_site = Site.objects.get_current()
            domain = current_site.domain
            protocol = 'https' if not settings.DEBUG else 'http'
        except:
            # Ultimate fallback - use ALLOWED_HOSTS or default
            allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
            if allowed_hosts and allowed_hosts[0] != '*':
                domain = allowed_hosts[0]
            else:
                domain = '20transformers.com'  # Default domain
            
            # Determine protocol based on domain
            protocol = 'https' if domain not in ['localhost', '127.0.0.1'] else 'http'
        
        verification_url = f"{protocol}://{domain}/accounts/continue-verification/"

    current_site = "20TF.com"
    email_body = (
        f"Hi {user.username},\n\n"
        f"Thanks for signing up on {current_site}. Please verify your email with the OTP passcode:\n\n"
        f"Your verification code: {otp_code}\n\n"
        f"Enter this code on the verification page to activate your account.\n\n"
        f"If you closed the verification page or need to continue verification, click this link:\n"
        f"{verification_url}\n\n"
        f"---\n"
        f"If you didn't request this, please ignore this email."
    )
    from_email = settings.DEFAULT_FROM_EMAIL

    try:
        email_message = EmailMessage(
            subject=subject,
            body=email_body,
            from_email=from_email,
            to=[email]
        )
        email_message.send(fail_silently=False)
    except Exception as e:
        # Log the error but don't fail the registration process
        logger.error(f"Failed to send OTP email to {email}: {str(e)}")
        # In production, you might want to handle this differently
        # For now, we'll let the registration continue



def send_normal_email(data):
    email=EmailMessage(
        subject=data['email_subject'],
        body=data['email_body'],
        from_email=settings.EMAIL_HOST_USER,
        to=[data['to_email']]
    )
    email.send()


def send_password_reset_email(user_email, context_data):
    subject = 'Password Reset Request'
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [user_email]

    html_content = render_to_string('registration/accounts/password_reset_email.html', context_data)
    email = EmailMultiAlternatives(subject, html_content, from_email, to)
    email.content_subtype = 'html'  # Important
    email.send()


def verify_recaptcha(request):
    """
    Verify Google reCAPTCHA response from the form submission.
    Returns True if verification succeeds, False otherwise.
    """
    recaptcha_response = request.POST.get('g-recaptcha-response')
    
    if not recaptcha_response:
        logger.warning("reCAPTCHA response missing")
        return False
    
    secret_key = settings.RECAPTCHA_SECRET_KEY
    site_key = settings.RECAPTCHA_SITE_KEY
    
    # If keys are not configured, skip verification (for development)
    if not secret_key or not site_key:
        logger.warning("reCAPTCHA keys not configured, skipping verification")
        return True  # Allow in development mode
    
    try:
        # Get client IP for additional verification
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            remoteip = x_forwarded_for.split(',')[0]
        else:
            remoteip = request.META.get('REMOTE_ADDR')
        
        # Verify with Google
        verify_data = {
            'secret': secret_key,
            'response': recaptcha_response,
            'remoteip': remoteip
        }
        
        response = requests.post(
            settings.RECAPTCHA_VERIFY_URL,
            data=verify_data,
            timeout=10
        )
        
        result = response.json()
        
        if result.get('success'):
            logger.info("reCAPTCHA verification successful")
            return True
        else:
            error_codes = result.get('error-codes', [])
            logger.warning(f"reCAPTCHA verification failed: {error_codes}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"reCAPTCHA verification request failed: {str(e)}")
        # On network error, we can either fail secure (return False) or fail open (return True)
        # Failing secure is safer but might block legitimate users if Google is down
        # For now, we'll fail secure
        return False
    except Exception as e:
        logger.error(f"reCAPTCHA verification error: {str(e)}")
        return False
