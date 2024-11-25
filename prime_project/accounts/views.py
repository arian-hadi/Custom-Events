from urllib import request
from django.shortcuts import render
from django.views.generic.edit import CreateView
from .forms import CustomUserCreationForm,EmailAuthenticationForm
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy('home')



class EmailLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'accounts/login.html'

    def get_success_url(self):
        return reverse_lazy('home')

class checkSessionView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return JsonResponse({"status" : "active"})




