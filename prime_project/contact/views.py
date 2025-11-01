from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.mail import EmailMessage, BadHeaderError
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
import logging

from .forms import ContactForm
from accounts.utils import verify_recaptcha

logger = logging.getLogger(__name__)

class ContactView(SuccessMessageMixin, FormView):
    template_name = "contact.html"
    form_class = ContactForm
    success_url = reverse_lazy("contact")  # make sure this matches your URL name
    success_message = "Your message has been sent successfully!"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recaptcha_site_key'] = settings.RECAPTCHA_SITE_KEY
        return context

    def form_valid(self, form):
        # Verify reCAPTCHA before processing contact form
        if not verify_recaptcha(self.request):
            messages.error(self.request, "Please complete the reCAPTCHA verification.")
            return self.form_invalid(form)
        
        name = form.cleaned_data["name"]
        subject = form.cleaned_data["subject"]
        email = form.cleaned_data["email"]
        message = form.cleaned_data["message"]

        full_message = (
            "NEW EMAIL FROM 2.0TRANSFORMERS SUPPORT\n\n"
            f"From : {name}\n"
            f"Email: {email}\n\n"
            f"Subject: {subject}\n\n"
            f"Message:\n{message}\n"
        )

        to_address = getattr(settings, "SUPPORT_INBOX", getattr(settings, "DEFAULT_FROM_EMAIL"))

        if not to_address:
            form.add_error(None, "No support inbox is configured.")
            return self.form_invalid(form)

        email_message = EmailMessage(
            subject=f"Contact Form: {subject}",
            body=full_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL"),
            to=[to_address],
            reply_to=[email],
        )

        try:
            sent_count = email_message.send(fail_silently=False)
            logger.info("Contact email queued result count=%s to=%s", sent_count, email_message.to)
            if sent_count == 0:
                messages.error(self.request, "The mail server did not accept the message.")
                return self.form_invalid(form)
        except BadHeaderError:
            form.add_error(None, "Invalid header found.")
            return self.form_invalid(form)
        except Exception:
            logger.exception("Contact form send failed")
            messages.error(self.request, "There was an error sending your message. Please try again later.")
            return self.form_invalid(form)

        # <-- IMPORTANT: on success, return a real response
        return super().form_valid(form)