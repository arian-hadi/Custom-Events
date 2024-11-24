from urllib import request
from django.shortcuts import render
from django.views.generic.edit import CreateView
from .forms import CustomUserCreationForm,EmailAuthenticationForm
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy('home')



class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'accounts/login.html'

    def get_success_url(self):
        return reverse_lazy('home')



