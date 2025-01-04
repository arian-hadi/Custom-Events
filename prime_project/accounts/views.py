from rest_framework.permissions import AllowAny,IsAuthenticated
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .serializers import UserRegisterSerializer,UserLoginSerializer,PasswordResetRequestSerializer,SetNewPasswordSerializer,LogoutUserSerializer
from rest_framework import status
from .utils import send_code_to_user
from .models import OneTimePassword, CustomUser
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import smart_str, DjangoUnicodeDecodeError

# class SignUpView(CreateView):
#     form_class = CustomUserCreationForm
#     template_name = "accounts/signup.html"
#     success_url = reverse_lazy('home')


# class EmailLoginView(LoginView):
#     authentication_form = EmailAuthenticationForm
#     template_name = 'accounts/login.html'

#     def get_success_url(self):
#         return reverse_lazy('home')

# class LogoutView(LogoutView):
#     next_page = reverse_lazy('login')

# class checkSessionView(LoginRequiredMixin, View):
#     def get(self, request, *args, **kwargs):
#         return JsonResponse({"status" : "active"})
    

# User = get_user_model()

# class CustomPasswordResetView(PasswordResetView):
#     email_template_name = 'registration/password_reset_email.html'
#     success_url = reverse_lazy('password_reset_done')
#     template_name = 'registration/password_reset_form.html'



class RegisterUserView(GenericAPIView):
    serializer_class = UserRegisterSerializer

    def post(self, request):
        user_data = request.data
        serializer = self.serializer_class(data = user_data)
        if serializer.is_valid(raise_exception=True):
            user_instance = serializer.save()
            send_code_to_user(user_instance.email)
            return Response({
                'data':serializer.data,
                'message': f'hi {user_instance.username} thanks for sigining up a passcode has been sent to your email'
            }, status = status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
    

class VerifyUserEmail(GenericAPIView):
    def post(self, request):
        otp_code = request.data.get('otp')
        if not otp_code:
            return Response({
                'message': "OTP not provided"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get the OTP object
            user_code_obj = OneTimePassword.objects.get(code=otp_code)
            
            # Access the related user
            user = user_code_obj.user
            
            if not user.is_verified:
                user.is_verified = True
                user.save()
                
                # Optionally, delete the OTP after verification
                user_code_obj.delete()

                return Response({
                    'message': "Email verification was successful!"
                }, status=status.HTTP_200_OK)
            
            return Response({
                'message': "User is already verified"
            }, status=status.HTTP_200_OK)

        except OneTimePassword.DoesNotExist:
            return Response({
                'message': "Invalid OTP"
            }, status=status.HTTP_404_NOT_FOUND)
        

class LoginUserView(GenericAPIView):
    serializer_class = UserLoginSerializer
    def post(self, request):
        serializer = self.serializer_class(data = request.data, context = {'request':request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status = status.HTTP_200_OK)
    

class TestingAuthenticatedView(GenericAPIView):
    permission_classes=[IsAuthenticated]

    def get(self, request):
         # Check if Authorization header is being received
        if request.user.is_authenticated:
            data = {'msg': 'it works'}
        else:
            data = {'msg': 'User is not authenticated'}
            print(f"User: {request.user}")  # Should display the authenticated user or AnonymousUser
            print(f"Headers: {request.headers}") 
        return Response(data, status=status.HTTP_200_OK)



class PasswordResetRequestView(GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    def post(self, request):
        serializer = self.serializer_class(data = request.data, context = {'request':request})
        serializer.is_valid(raise_exception = True)
        return Response({'message':'we have sent you a an email link to reset your password'}, status=status.HTTP_200_OK)


class PasswordResetConfirm(GenericAPIView):

    def get(self, request, uidb64, token):
        try:
            user_id=smart_str(urlsafe_base64_decode(uidb64))
            user=CustomUser.objects.get(id=user_id)

            if not PasswordResetTokenGenerator().check_token(user, token):
                return Response({'message':'token is invalid or has expired'}, status=status.HTTP_401_UNAUTHORIZED)
            return Response({'success':True, 'message':'credentials is valid', 'uidb64':uidb64, 'token':token}, status=status.HTTP_200_OK)

        except DjangoUnicodeDecodeError as identifier:
            return Response({'message':'token is invalid or has expired'}, status=status.HTTP_401_UNAUTHORIZED)

class SetNewPasswordView(GenericAPIView):
    serializer_class= SetNewPasswordSerializer

    def patch(self, request):
        serializer=self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'success':True, 'message':"password reset is succesful"}, status=status.HTTP_200_OK)

class LogoutApiView(GenericAPIView):
    serializer_class=LogoutUserSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer=self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)