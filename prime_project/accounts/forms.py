from django import forms
from .models import CustomUser
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
import logging
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)
User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['email', 'username']  # Updated to only include email and username (since 'display_username' was removed)

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
    
class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(  # Keep this as username but change the field name in template
        widget=forms.EmailInput(attrs={
            'class': 'mt-1 block w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg text-sm',
            'placeholder': 'Enter your email'
        })
    )
    
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'mt-1 block w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg text-sm',
        'placeholder': 'Enter your password'
    }))

    def clean(self):
        username = self.cleaned_data.get('username')  # This is actually the email
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(
                self.request, username=username, password=password)
            if self.user_cache is None:
                raise ValidationError(
                    'Invalid email or password.',
                    code='invalid_login'
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class CustomPasswordResetForm(PasswordResetForm):
    def save(self, *args, **kwargs):
        user = self.get_users(self.cleaned_data["email"])
        for u in user:
            logger.info(f"User ID: {u.id}, Email: {u.email}")
        super().save(*args, **kwargs)


class OTPVerificationForm(forms.Form):
    otp_code = forms.CharField(
        label = "Enter OTP",
        max_length = 6,
        min_length = 6,
        widget=forms.TextInput(attrs={'placeholder': 'Enter 6-digit OTP'})
    )
