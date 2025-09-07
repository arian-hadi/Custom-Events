from django import forms

BASE_INPUT = "mt-1 block w-full rounded-xl border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 px-4 py-2"
BASE_TEXTAREA = "mt-1 block w-full rounded-xl border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 px-4 py-3 min-h-[8rem]"

class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Name / Username"})
    )
    email = forms.EmailField(
        max_length=150,
        widget=forms.EmailInput(attrs={"class": BASE_INPUT, "placeholder": "Email"})
    )
    subject = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Subject"})
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"class": BASE_TEXTAREA, "placeholder": "Write Message . . ."})
    )

    # Honeypot
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""
