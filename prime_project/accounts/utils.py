import random 
from django.core.mail import EmailMessage
from .models import CustomUser,OneTimePassword
from django.conf import settings

def generateOtp():
    otp = ""
    for _ in range(6):
        otp += str(random.randint(1,9))
    return otp

def send_code_to_user(email):
    subject = "One-Time Passcode for Email Verification"
    otp_code = generateOtp()

    try:
        user = CustomUser.objects.get(email=email)
    except CustomUser.DoesNotExist:
        raise ValueError("User with this email does not exist")

    # Delete any old OTPs before creating a new one
    OneTimePassword.objects.filter(user=user).delete()

    OneTimePassword.objects.create(user=user, code=otp_code)

    current_site = "20TF.com"
    email_body = (
        f"Hi {user.username},\n\n"
        f"Thanks for signing up on {current_site}. Please verify your email with the OTP passcode:\n\n"
        f"{otp_code}\n\n"
        "If you didn't request this, please ignore this email."
    )
    from_email = settings.DEFAULT_FROM_EMAIL

    email_message = EmailMessage(
        subject=subject,
        body=email_body,
        from_email=from_email,
        to=[email]
    )
    email_message.send(fail_silently=False)



def send_normal_email(data):
    email=EmailMessage(
        subject=data['email_subject'],
        body=data['email_body'],
        from_email=settings.EMAIL_HOST_USER,
        to=[data['to_email']]
    )
    email.send()