from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from shop.models import SiteLogo


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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site_logo'] = SiteLogo.get_active_logo()
        return context


class TermOfServiceView(TemplateView):
    template_name = "core/terms_of_service.html"

class PrivacyPolicyView(TemplateView):
    template_name = "core/privacy_policy.html"

class AboutView(TemplateView):
    template_name = "core/about.html"

class DisclaimersView(TemplateView):
    template_name = "core/disclaimers.html"
    