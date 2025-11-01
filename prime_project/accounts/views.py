from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy,reverse, NoReverseMatch
from django.shortcuts import render, redirect
from django.views.generic import CreateView, View
from django.contrib import messages
from django.contrib.auth import login
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from .forms import CustomUserCreationForm, EmailAuthenticationForm, CustomPasswordResetForm, OTPVerificationForm
from .models import OneTimePassword, CustomUser
from .utils import send_code_to_user, verify_recaptcha
import logging
from django_ratelimit.decorators import ratelimit
import os, requests, time
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings

logger = logging.getLogger(__name__)

def create_too_many_requests_response(message="Too many requests"):
    response = HttpResponse(message, content_type='text/plain')
    response.status_code = 429
    return response

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def is_rate_limited(request, key_suffix='', limit=5, period=300):
    try:
        client_ip = get_client_ip(request)
        cache_key = f"ratelimit:{client_ip}:{key_suffix}"
        current_count = cache.get(cache_key, 0) or 0
        if current_count >= limit:
            return True
        cache.set(cache_key, current_count + 1, period)
        return False
    except Exception as e:
        logger.warning("Rate limit cache error: %s", e)
        # In production, if cache fails, be more permissive to avoid blocking users
        return False  # degrade gracefully

# # Turnstile verification (keeping your existing function)
# def verify_turnstile(request) -> bool:
#     token = request.POST.get("cf-turnstile-response")
#     secret = os.environ.get("TURNSTILE_SECRET_KEY")
#     if not token or not secret:
#         return False
#     try:
#         resp = requests.post(
#             "https://challenges.cloudflare.com/turnstile/v0/siteverify",
#             data={
#                 "secret": secret,
#                 "response": token,
#                 "remoteip": get_client_ip(request),
#             },
#             timeout=5,
#         )
#         data = resp.json()
#         return bool(data.get("success"))
#     except Exception:
#         return False


@method_decorator([csrf_protect, never_cache], name='dispatch')
class RegisterUserView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        # Rate limiting relaxed - reCAPTCHA handles bot protection
        # Only rate-limit POSTs (actual sign-up attempts), not GET page views
        # Increased limit significantly since reCAPTCHA protects against bots
        if request.method == "POST" and is_rate_limited(request, 'register_post', limit=50, period=3600):
            messages.error(request, "Too many registration attempts. Please try again later.")
            return render(request, self.template_name, {
                'form': self.form_class(),
                'rate_limited': True,
                'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY
            })
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recaptcha_site_key'] = settings.RECAPTCHA_SITE_KEY
        return context

    def form_valid(self, form):
        # Verify reCAPTCHA before processing registration
        if not verify_recaptcha(self.request):
            messages.error(self.request, "Please complete the reCAPTCHA verification.")
            return self.form_invalid(form)
        
        # Additional server-side validation
        email = form.cleaned_data["email"].lower()
        username = form.cleaned_data["username"]
        
        # Double-check for existing users (race condition protection)
        if CustomUser.objects.filter(email=email).exists():
            form.add_error("email", "A user with this email already exists.")
            return self.form_invalid(form)
            
        if CustomUser.objects.filter(username__iexact=username).exists():
            form.add_error("username", "A user with this username already exists.")
            return self.form_invalid(form)

        # Log registration attempt for monitoring
        client_ip = get_client_ip(self.request)
        cache.delete(f"ratelimit:{client_ip}:register_post")

        try:
            user = form.save(commit=False)
            user.username = username
            user.is_active = False
            user.save()

            logger.info(f"User created: {user.email}")

            self.request.session["user_email"] = user.email
            self.request.session["registration_time"] = int(time.time())

            # Try to send OTP email, but don't fail registration if it fails
            try:
                send_code_to_user(user.email, request=self.request)
                messages.success(self.request, "Account created! Please check your email for verification code.")
            except Exception as email_error:
                logger.error(f"Failed to send OTP email: {str(email_error)}")
                messages.warning(self.request, "Account created! However, there was an issue sending the verification email. Please try logging in or contact support.")

            return redirect('verify_email')
            
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            messages.error(self.request, "Registration failed. Please try again.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        # Log failed registration attempts
        client_ip = get_client_ip(self.request)
        logger.warning(f"Failed registration attempt from IP {client_ip}")
        return super().form_invalid(form)


@method_decorator([csrf_protect, never_cache], name='dispatch')
class VerifyUserEmail(View):
    def dispatch(self, request, *args, **kwargs):
        # Rate limiting relaxed - reCAPTCHA handles bot protection
        # Increased limit significantly for legitimate users
        if is_rate_limited(request, 'otp_verify', limit=50, period=3600):
            messages.error(request, "Too many verification attempts. Please try again later.")
            return redirect("signup")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        user_email = request.session.get("user_email")
        registration_time = request.session.get("registration_time")
        
        if not user_email:
            messages.error(request, "Session expired. Please register again.")
            return redirect("signup")

        # Check if session is too old (2 hours)
        if registration_time and (int(time.time()) - registration_time > 7200):
            request.session.flush()
            messages.error(request, "Verification session expired. Please register again.")
            return redirect("signup")

        form = OTPVerificationForm()
        return render(request, "accounts/verify_email.html", {"form": form})

    def post(self, request):
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data["otp_code"]
            user_email = request.session.get("user_email")

            if not user_email:
                messages.error(request, "Session expired. Please register again.")
                return redirect("signup")

            try:
                user = CustomUser.objects.get(email=user_email)
                
                # Check for too many failed OTP attempts for this user
                failed_attempts_key = f"otp_failed:{user.email}"
                failed_attempts = cache.get(failed_attempts_key, 0)
                
                if failed_attempts >= 5:
                    messages.error(request, "Too many failed attempts. Please request a new OTP.")
                    return render(request, "accounts/verify_email.html", {"form": form})

                otp_entry = OneTimePassword.objects.filter(user=user, code=otp_code).first()

                if not otp_entry or otp_entry.is_expired():
                    # Increment failed attempts
                    cache.set(failed_attempts_key, failed_attempts + 1, 3600)
                    messages.error(request, f"Invalid or expired OTP. {4-failed_attempts} attempts remaining.")
                    return render(request, "accounts/verify_email.html", {"form": form})

                # Success! Clear failed attempts and activate user
                cache.delete(failed_attempts_key)
                user.is_verified = True
                user.is_active = True
                user.save(update_fields=["is_active", "is_verified"])
                otp_entry.delete()

                # Clear session
                request.session.pop("user_email", None)
                request.session.pop("registration_time", None)

                logger.info(f"Email verified successfully for user: {user.email}")
                messages.success(request, "Email verified successfully! You can now log in.")
                return redirect("login")

            except CustomUser.DoesNotExist:
                messages.error(request, "User does not exist.")

        return render(request, "accounts/verify_email.html", {"form": form})


@method_decorator([csrf_protect, never_cache], name='dispatch')
class ResendOTPView(View):
    def dispatch(self, request, *args, **kwargs):
        # Rate limiting relaxed - reCAPTCHA handles bot protection
        # Increased limit significantly for legitimate users
        if is_rate_limited(request, 'otp_resend', limit=20, period=3600):
            messages.error(request, "Too many resend requests. Please try again later.")
            return redirect("verify_email")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        email = request.session.get("user_email")
        if not email:
            messages.error(request, "Session expired. Please sign up again.")
            return redirect("signup")

        try:
            user = CustomUser.objects.get(email=email)
            
            # Check last resend time to prevent spam
            last_resend_key = f"last_resend:{user.email}"
            last_resend = cache.get(last_resend_key)
            
            if last_resend and (int(time.time()) - last_resend < 60):  # 1 minute cooldown
                messages.error(request, "Please wait before requesting another code.")
                return redirect("verify_email")
            
            send_code_to_user(user.email, request=request)
            cache.set(last_resend_key, int(time.time()), 300)  # 5 minute cache
            messages.success(request, "A new OTP has been sent to your email.")
            
        except CustomUser.DoesNotExist:
            messages.error(request, "User not found.")

        return redirect("verify_email")


@method_decorator([csrf_protect, never_cache], name='dispatch')
class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'accounts/login.html'


    def dispatch(self, request, *args, **kwargs):
        # Rate limiting relaxed - reCAPTCHA handles bot protection
        # Only rate-limit POSTs (login submissions), not viewing the login page
        # Increased limit significantly since reCAPTCHA protects against bots
        if request.method == "POST" and is_rate_limited(request, 'login_post', limit=50, period=3600):
            messages.error(request, "Too many login attempts. Please try again later.")
            return render(request, self.template_name, {
                'form': self.authentication_form(),
                'rate_limited': True,
                'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY
            })
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recaptcha_site_key'] = settings.RECAPTCHA_SITE_KEY
        return context

    def form_valid(self, form):
        # Verify reCAPTCHA before processing login
        if not verify_recaptcha(self.request):
            messages.error(self.request, "Please complete the reCAPTCHA verification.")
            return self.form_invalid(form)
        
        try:
            # Debug form data before authentication
            logger.info(f"Login form data: {form.cleaned_data}")
            
            user = form.get_user()
            if not user:
                logger.warning("No user returned from form.get_user()")
                messages.error(self.request, "Invalid email or password.")
                return self.form_invalid(form)
                
            client_ip = get_client_ip(self.request)
            cache.delete(f"ratelimit:{client_ip}:login_post")
            logger.info("Attempting login for user_id=%s", user.pk)

            if not user.is_verified:
                logger.warning(f"User {user.email} is not verified")
                messages.error(self.request, "Please verify your email before logging in.")
                return self.form_invalid(form)

            if not user.is_active:
                logger.warning(f"User {user.email} is not active")
                messages.error(self.request, "Your account is not active.")
                return self.form_invalid(form)

            login(self.request, user)
            logger.info(f"User {user.email} logged in successfully.")

            cache.delete(f"login_failed:{client_ip}")

            if user.is_admin():
                next_name = 'dashboard:admin_dashboard'
            else:
                next_name = 'dashboard:user_dashboard'

            try:
                reverse(next_name)  # explode early if missing in prod
                return redirect(next_name)
            except NoReverseMatch:
                logger.exception("Missing URL name for post-login redirect: %s", next_name)
                messages.error(self.request, "Dashboard is temporarily unavailable.")
                return redirect('login')
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            messages.error(self.request, "Login failed. Please try again.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        client_ip = get_client_ip(self.request)
        logger.warning(f"Login failed from IP {client_ip}")
        
        # Debug form errors
        if form.errors:
            logger.warning(f"Form errors: {form.errors}")
        
        # Debug form data
        logger.warning(f"Form data: {form.data}")
        
        messages.error(self.request, "Invalid email or password.")
        return super().form_invalid(form)


@method_decorator([csrf_protect, never_cache], name='dispatch')
class ContinueVerificationView(View):
    def dispatch(self, request, *args, **kwargs):
        # Rate limiting relaxed - reCAPTCHA handles bot protection
        # Increased limit significantly for legitimate users
        if is_rate_limited(request, 'continue_verify', limit=30, period=3600):
            messages.error(request, "Too many attempts. Please try again later.")
            return render(request, "accounts/continue_verification.html", {'rate_limited': True})
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, "accounts/continue_verification.html")

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        
        if not email:
            messages.error(request, "Please enter an email address.")
            return render(request, "accounts/continue_verification.html")

        try:
            user = CustomUser.objects.get(email=email)
            if user.is_verified:
                messages.info(request, "This account is already verified.")
                return redirect("login")
            
            # Restore session and send new OTP
            request.session["user_email"] = email
            request.session["registration_time"] = int(time.time())
            
            # Send new OTP so user can verify
            try:
                send_code_to_user(user.email, request=request)
                messages.success(request, f"A new verification code has been sent to {email}. Please check your email and enter the code to verify.")
            except Exception as e:
                logger.error(f"Failed to send OTP during continue verification: {str(e)}")
                messages.warning(request, "Session restored, but failed to send verification code. Please try resending from the verification page.")
            
            return redirect("verify_email")
            
        except CustomUser.DoesNotExist:
            messages.error(request, "No account found with this email.")
            return redirect("continue_verification")


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')


@method_decorator([csrf_protect, never_cache], name='dispatch')
class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    email_template_name = 'registration/password_reset_email.txt'
    html_email_template_name = 'registration/password_reset_email.html'
    success_url = reverse_lazy('password_reset_done')
    template_name = 'registration/password_reset_form.html'

    def dispatch(self, request, *args, **kwargs):
        # Rate limiting relaxed - reCAPTCHA handles bot protection
        # Increased limit significantly for legitimate users
        if is_rate_limited(request, 'password_reset', limit=30, period=3600):
            messages.error(request, "Too many password reset attempts. Please try again later.")
            return render(request, self.template_name, {
                'form': self.form_class(),
                'rate_limited': True
            })
        return super().dispatch(request, *args, **kwargs)


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    success_url = reverse_lazy('password_reset_complete')
    template_name = 'registration/password_reset_confirm.html'