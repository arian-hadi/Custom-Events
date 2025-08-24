from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.mail import EmailMessage, BadHeaderError
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
import logging

from .forms import ContactForm

logger = logging.getLogger(__name__)

class ContactView(SuccessMessageMixin, FormView):
    template_name = "contact.html"
    form_class = ContactForm
    success_url = reverse_lazy("contact")  # make sure this matches your URL name
    success_message = "Your message has been sent successfully!"

    def form_valid(self, form):
        subject = form.cleaned_data["subject"]
        email = form.cleaned_data["email"]
        message = form.cleaned_data["message"]

        full_message = (
            "NEW EMAIL FROM 2.0TRANSFORMERS SUPPORT\n\n"
            f"Subject: {subject}\n"
            f"Email: {email}\n\n"
            f"Message:\n{message}\n"
        )

        # Prefer a dedicated support inbox; fall back to DEFAULT_FROM_EMAIL
        to_address = getattr(settings, "SUPPORT_INBOX", getattr(settings, "DEFAULT_FROM_EMAIL", None))

        email_message = EmailMessage(
            subject=f"Contact Form: {subject}",
            body=full_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to_address] if to_address else None,
            reply_to=[email],  # note: reply_to (not replay_to)
        )

        try:
            email_message.send(fail_silently=False)
        except BadHeaderError:
            form.add_error(None, "Invalid header found.")
            return self.form_invalid(form)
        except Exception:
            logger.exception("Contact form send failed")
            messages.error(self.request, "There was an error sending your message. Please try again later.")
            return self.form_invalid(form)

        return super().form_valid(form)
