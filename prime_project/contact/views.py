from mailjet_rest import Client
import os
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import reverse
from django.views.generic import TemplateView, FormView
from .forms import ContactForm
from prime_project.localsettings import email_address


class SuccessView(TemplateView):
    template_name = "success.html"


class ContactView(FormView):
    form_class = ContactForm
    template_name = "contact.html"

    def get_success_url(self):
        return reverse("contact")

    def form_valid(self, form):
        email = form.cleaned_data.get("email")
        subject = form.cleaned_data.get("subject")
        message = form.cleaned_data.get("message")

        # Mailjet API configuration
        mailjet = Client(auth=(settings.EMAIL_HOST_API, settings.EMAIL_HOST_SECRET_KEY), version='v3.1')
        data = {
            'Messages': [
                {
                    "From": {
                        "Email": email_address
                        
                    },
                    "To": [
                        {
                            "Email": email_address                         
                        }
                    ],
                    "Subject": subject,
                    "TextPart": message,
                    "HTMLPart": f"<h3>{message}</h3>",
                }
            ]
        }

        # Send email
        result = mailjet.send.create(data=data)
        print(result.status_code)  # Check the HTTP response code
        print(result.json())  # Inspect the full response

        if result.status_code == 200:
            return super(ContactView, self).form_valid(form)
        else:
            return self.form_invalid(form)