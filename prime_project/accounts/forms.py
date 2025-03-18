from django import forms
from .models import CustomUser
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
import logging

logger = logging.getLogger(__name__)

class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ['email', 'username'] 
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
    username = forms.EmailField(label="Email")  # Rename field but internally still 'username'

    def clean(self):
        """Override the clean method to properly authenticate using email."""
        email = self.cleaned_data.get("username")  # 'username' refers to email
        password = self.cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(email=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Invalid email or password.")

        return self.cleaned_data


User = get_user_model()

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
