from django.shortcuts import render

from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response

class HomeView(TemplateView):
    template_name = "core/core.html"

class HomeAPIView(APIView):
    def get(self, request):
        data = {
            "message": "Welcome to the core app",
            "info": "Landing page API",
        }
        return Response(data)