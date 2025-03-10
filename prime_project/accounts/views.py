# from rest_framework.permissions import AllowAny,IsAuthenticated
# from rest_framework.generics import GenericAPIView
# from rest_framework.response import Response
# from rest_framework.decorators import api_view
# from .serializers import UserRegisterSerializer,UserLoginSerializer,PasswordResetRequestSerializer,SetNewPasswordSerializer,LogoutUserSerializer
# from rest_framework import status

# class RegisterUserView(GenericAPIView):
#     serializer_class = UserRegisterSerializer

#     def post(self, request):
#         user_data = request.data
#         serializer = self.serializer_class(data = user_data)
#         if serializer.is_valid(raise_exception=True):
#             user_instance = serializer.save()
#             send_code_to_user(user_instance.email)
#             return Response({
#                 'data':serializer.data,
#                 'message': f'hi {user_instance.username} thanks for sigining up a passcode has been sent to your email'
#             }, status = status.HTTP_201_CREATED)
        
#         return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
    

# class VerifyUserEmail(GenericAPIView):
#     def post(self, request):
#         otp_code = request.data.get('otp')
#         if not otp_code:
#             return Response({
#                 'message': "OTP not provided"
#             }, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             # Get the OTP object
#             user_code_obj = OneTimePassword.objects.get(code=otp_code)
            
#             # Access the related user
#             user = user_code_obj.user
            
#             if not user.is_verified:
#                 user.is_verified = True
#                 user.save()
                
#                 # Optionally, delete the OTP after verification
#                 user_code_obj.delete()

#                 return Response({
#                     'message': "Email verification was successful!"
#                 }, status=status.HTTP_200_OK)
            
#             return Response({
#                 'message': "User is already verified"
#             }, status=status.HTTP_200_OK)

#         except OneTimePassword.DoesNotExist:
#             return Response({
#                 'message': "Invalid OTP"
#             }, status=status.HTTP_404_NOT_FOUND)
        

# class LoginUserView(GenericAPIView):
#     serializer_class = UserLoginSerializer
#     def post(self, request):
#         serializer = self.serializer_class(data = request.data, context = {'request':request})
#         serializer.is_valid(raise_exception=True)
#         return Response(serializer.data, status = status.HTTP_200_OK)
    

# class TestingAuthenticatedView(GenericAPIView):
#     permission_classes=[IsAuthenticated]

#     def get(self, request):
#          # Check if Authorization header is being received
#         if request.user.is_authenticated:
#             data = {'msg': 'it works'}
#         else:
#             data = {'msg': 'User is not authenticated'}
#             print(f"User: {request.user}")  # Should display the authenticated user or AnonymousUser
#             print(f"Headers: {request.headers}") 
#         return Response(data, status=status.HTTP_200_OK)



# class PasswordResetRequestView(GenericAPIView):
#     serializer_class = PasswordResetRequestSerializer
#     def post(self, request):
#         serializer = self.serializer_class(data = request.data, context = {'request':request})
#         serializer.is_valid(raise_exception = True)
#         return Response({'message':'we have sent you a an email link to reset your password'}, status=status.HTTP_200_OK)


# class PasswordResetConfirm(GenericAPIView):

#     def get(self, request, uidb64, token):
#         try:
#             user_id=smart_str(urlsafe_base64_decode(uidb64))
#             user=CustomUser.objects.get(id=user_id)

#             if not PasswordResetTokenGenerator().check_token(user, token):
#                 return Response({'message':'token is invalid or has expired'}, status=status.HTTP_401_UNAUTHORIZED)
#             return Response({'success':True, 'message':'credentials is valid', 'uidb64':uidb64, 'token':token}, status=status.HTTP_200_OK)

#         except DjangoUnicodeDecodeError as identifier:
#             return Response({'message':'token is invalid or has expired'}, status=status.HTTP_401_UNAUTHORIZED)

# class SetNewPasswordView(GenericAPIView):
#     serializer_class= SetNewPasswordSerializer

#     def patch(self, request):
#         serializer=self.serializer_class(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         return Response({'success':True, 'message':"password reset is succesful"}, status=status.HTTP_200_OK)

# class LogoutApiView(GenericAPIView):
#     serializer_class=LogoutUserSerializer
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         serializer=self.serializer_class(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         serializer.save()
#         return Response(status=status.HTTP_204_NO_CONTENT)

from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.views.generic import CreateView, View
from django.contrib import messages
from django.contrib.auth import login
from .forms import CustomUserCreationForm, EmailAuthenticationForm, CustomPasswordResetForm,OTPVerificationForm
from .models import OneTimePassword, CustomUser
from .utils import send_code_to_user


class RegisterUserView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy('login')  

    def form_valid(self, form):
        user = form.save(commit=False)
        user.username = form.cleaned_data["username"]  
        user.email = form.cleaned_data["email"] 
        user.is_active = False  
        user.save()

        #print(f"Sending email to: {user.email}")  

        if not user.email or "@" not in user.email:  
            return self.form_invalid(form)

        self.request.session["user_email"] = user.email 

        send_code_to_user(user.email) 
        messages.success(self.request, "OTP sent! Please check your email.")

        return redirect('verify_email')  


# ✅ Verify Email View (Using OTP)
class VerifyUserEmail(View):
    def get(self, request):
        user_email = request.session.get("user_email")
        if not user_email:
            messages.error(request, "Session expired. Please request a new OTP.")
            return redirect("signup")  # Prevent stuck users

        form = OTPVerificationForm()
        return render(request, "accounts/verify_email.html", {"form": form})

    def post(self, request):
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data["otp_code"]
            user_email = request.session.get("user_email")

            if not user_email:
                messages.error(request, "Session expired. Please request a new OTP.")
                return redirect("signup")

            try:
                user = CustomUser.objects.get(email=user_email)
                otp_entry = OneTimePassword.objects.filter(user=user, code=otp_code).first()

                if not otp_entry or otp_entry.is_expired():
                    messages.error(request, "Invalid or expired OTP. Please try again.")
                    return render(request, "accounts/verify_email.html", {"form": form})

                # ✅ OTP is valid! Activate the user
                user.is_verified = True
                user.is_active = True  
                user.save(update_fields=["is_active", "is_verified"]) 
                otp_entry.delete()  # Remove OTP after successful verification

                # ✅ Clear session after successful verification
                request.session.pop("user_email", None)

                messages.success(request, "Email verified successfully! You can now log in.")
                return redirect("login")

            except CustomUser.DoesNotExist:
                messages.error(request, "User does not exist.")

        return render(request, "accounts/verify_email.html", {"form": form})


# ✅ Login View (Using Your `EmailAuthenticationForm`)
class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'accounts/login.html'

    def get_success_url(self):
        return reverse_lazy('home')  # Redirect to home page after login

# ✅ Logout View
class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')  # Redirect to login page after logout

# ✅ Password Reset View (Using Your `CustomPasswordResetForm`)
class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm  # Use your custom form
    email_template_name = 'registration/password_reset_email.html'
    success_url = reverse_lazy('password_reset_done')
    template_name = 'registration/password_reset_form.html'

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    success_url = reverse_lazy('password_reset_complete')
    template_name = 'registration/password_reset_confirm.html'