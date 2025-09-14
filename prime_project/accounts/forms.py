# forms.py
from django import forms
from .models import CustomUser
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import logging, re, time

logger = logging.getLogger(__name__)

SAFE_USERNAME = re.compile(r'^[a-zA-Z0-9._-]{3,30}$')
URL_LIKE = re.compile(r'(https?://|www\.)', re.I)

# Spam patterns for username/content detection
SPAM_PATTERNS = [
    re.compile(r'\b(viagra|casino|poker|lottery|winner|congratulations)\b', re.I),
    re.compile(r'\b(click here|visit now|limited time|act now|free money)\b', re.I),
    re.compile(r'[0-9]{8,}', re.I),  # Long number sequences
    re.compile(r'(.)\1{4,}', re.I),   # Repeated characters (aaaaa, 11111)
]

# Optional: enable MX check - Disabled for production deployment
ENABLE_MX_CHECK = False  # Set to True if you install dnspython
try:
    import dns.resolver  # pip install dnspython
    # Only enable MX check in development, not in production
    import os
    if os.getenv('DEBUG', 'False').lower() == 'true':
        ENABLE_MX_CHECK = True
except ImportError:
    pass

def extract_domain(email: str) -> str:
    _, _, domain = email.strip().lower().rpartition("@")
    return domain.strip(".")

def has_mx(domain: str) -> bool:
    if not ENABLE_MX_CHECK:
        return True
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False

def is_blocked_domain(email: str) -> bool:
    """Check against specific blocked domains and patterns"""
    domain = extract_domain(email)
    
    # Specific domains known for spam
    blocked_domains = {
        # Russian domains commonly used for spam
        'mail.ru', 'yandex.ru', 'rambler.ru', 'list.ru',
        # Suspicious TLD patterns
        'example.xyz', 'test.tk', 'spam.ml', 'fake.ga',
        # Add specific problematic domains you've encountered
    }
    
    # Check exact domain matches
    if domain in blocked_domains:
        return True
    
    # Check for suspicious TLD patterns (but allow major providers)
    suspicious_tlds = ['.ru', '.xyz', '.top', '.su', '.tk', '.ml', '.ga', '.cf']
    
    # Allow major email providers even with suspicious TLDs
    major_providers = {
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 
        'icloud.com', 'aol.com', 'protonmail.com', 'tutanota.com'
    }
    
    # If it's a major provider, always allow
    if domain in major_providers:
        return False
    
    # Check for suspicious TLD endings
    for tld in suspicious_tlds:
        if domain.endswith(tld):
            return True
    
    return False

def is_disposable_email(email: str) -> bool:
    """Check against common disposable email providers"""
    domain = extract_domain(email)
    disposable_domains = {
        '10minutemail.com', 'guerrillamail.com', 'mailinator.com', 
        'temp-mail.org', 'throwaway.email', 'yopmail.com',
        'tempail.com', 'getnada.com', 'maildrop.cc', 'sharklasers.com',
        'tempmail.org', 'tempmail.net', '1secmail.com', 'dispostable.com',
        'mohmal.com', 'emailondeck.com', 'getairmail.com', 'fakeinbox.com'
    }
    return domain in disposable_domains

def contains_spam_patterns(text: str) -> bool:
    """Check if text contains spam-like patterns"""
    if not text:
        return False
    return any(pattern.search(text) for pattern in SPAM_PATTERNS)

class CustomUserCreationForm(UserCreationForm):
    # Multiple honeypot fields with different names
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    url = forms.CharField(required=False, widget=forms.HiddenInput) 
    phone = forms.CharField(required=False, widget=forms.HiddenInput)
    
    # Time-based protection
    timestamp = forms.CharField(widget=forms.HiddenInput, required=False)

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ["email", "username"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set timestamp when form is created
        self.fields['timestamp'].initial = str(int(time.time()))

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        
        # Basic validation
        if not SAFE_USERNAME.fullmatch(username):
            raise ValidationError("Usernames may contain letters, numbers, ., _, - (3–30 chars).")
        
        # Check for URLs and spam patterns
        if URL_LIKE.search(username) or contains_spam_patterns(username):
            raise ValidationError("Username contains prohibited content.")
        
        # Check for suspicious patterns
        if username.lower() in ['admin', 'administrator', 'test', 'user', 'guest']:
            raise ValidationError("This username is not allowed.")
            
        # Check for existing username (case insensitive)
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with this username already exists.")
            
        return username

    def clean_email(self):
        raw = (self.cleaned_data.get("email") or "").strip().lower()
        validate_email(raw)  # syntax check
        domain = extract_domain(raw)

        # Check for existing email
        if CustomUser.objects.filter(email=raw).exists():
            raise ValidationError("A user with this email already exists.")

        # Check for blocked domains
        if is_blocked_domain(raw):
            raise ValidationError("Sorry, this email domain is not allowed.")

        # Check for disposable email services
        if is_disposable_email(raw):
            raise ValidationError("Disposable email addresses are not allowed. Please use a permanent email address.")

        # Check for spam patterns in email
        if contains_spam_patterns(raw):
            raise ValidationError("Email address contains prohibited content.")

        # Check for suspicious email patterns
        local_part = raw.split('@')[0]
        
        # Check for numbers-only local part
        if local_part.isdigit():
            raise ValidationError("Email addresses with only numbers are not allowed.")
        
        # Check for very long number sequences
        if re.search(r'\d{6,}', local_part):
            raise ValidationError("Email address contains suspicious number patterns.")

        # MX record check (if enabled)
        if ENABLE_MX_CHECK and not has_mx(domain):
            raise ValidationError("Email domain has no valid MX records.")

        return raw

    def clean_timestamp(self):
        timestamp_str = self.cleaned_data.get('timestamp', '')
        if not timestamp_str:
            return timestamp_str
            
        try:
            form_time = int(timestamp_str)
            current_time = int(time.time())
            time_diff = current_time - form_time
            
            # Form filled too quickly (likely bot) - reduced to 3 seconds
            if time_diff < 3:
                raise ValidationError("Please take a moment to fill the form carefully.")
                
            # Form too old (prevent replay attacks)
            if time_diff > 3600:  # 1 hour
                raise ValidationError("Form expired. Please refresh and try again.")
                
        except (ValueError, TypeError):
            raise ValidationError("Invalid form timestamp.")
            
        return timestamp_str

    def clean(self):
        cleaned = super().clean()

        # Multiple honeypot checks
        honeypots = ['website', 'url', 'phone']
        for field in honeypots:
            if (cleaned.get(field) or "").strip():
                raise ValidationError("Registration blocked due to spam detection.")

        # Password match check
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
            
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'autofocus': True})
    )

    def clean_username(self):
        email = self.cleaned_data.get('username', '').strip().lower()
        validate_email(email)
        return email


class CustomPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'})
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        validate_email(email)
        
        # Check if user exists and is active
        if not CustomUser.objects.filter(email=email, is_active=True).exists():
            raise ValidationError("No active account found with this email address.")
            
        return email


class OTPVerificationForm(forms.Form):
    otp_code = forms.CharField(
        label="Verification Code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter 6-digit code',
            'class': 'text-center text-lg tracking-widest'
        })
    )

    def clean_otp_code(self):
        code = self.cleaned_data.get('otp_code', '').strip()
        if not code.isdigit():
            raise ValidationError("OTP must contain only numbers.")
        if len(code) != 6:
            raise ValidationError("OTP must be exactly 6 digits.")
        return code