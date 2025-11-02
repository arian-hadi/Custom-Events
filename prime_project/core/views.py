from django.shortcuts import render, redirect
from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = "core/core.html"
    
    def dispatch(self, request, *args, **kwargs):
        # Redirect logged-in users to their dashboard
        if request.user.is_authenticated:
            if request.user.role == 'admin':
                return redirect('dashboard:admin_dashboard')
            else:
                return redirect('dashboard:user_dashboard')
        return super().dispatch(request, *args, **kwargs)


class TermOfServiceView(TemplateView):
    template_name = "core/terms_of_service.html"

class PrivacyPolicyView(TemplateView):
    template_name = "core/privacy_policy.html"
    