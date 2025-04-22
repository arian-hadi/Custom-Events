from django.shortcuts import render
from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = "core/core.html"


class TermOfServiceView(TemplateView):
    template_name = "core/terms_of_service.html"

class PrivacyPolicyView(TemplateView):
    template_name = "core/privacy_policy.html"
    