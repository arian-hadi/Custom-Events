from django import forms
from .models import CustomUser
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['email', 'username']  # Since 'email' is your login field

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])  # Hash the password
        if commit:
            user.save()
        return user
    
class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email")  # Override the default username field with email

    def clean(self):
        """Override clean to authenticate using email."""
        email = self.cleaned_data.get("username")  # Here 'username' stores email due to form field label
        password = self.cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(username=email, password=password)  # Use 'email' explicitly
            if self.user_cache is None:
                raise forms.ValidationError("Invalid email or password.")
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
