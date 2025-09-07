from django import forms

class ContactForm(forms.Form):
    name = forms.CharField(max_length=120)
    subject = forms.CharField(max_length =150)   
    email = forms.EmailField(max_length=150)
    message = forms.CharField(widget=forms.Textarea)


    website = forms.CharField(required = False, widget=forms.HiddenInput)

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam Detected")
        return ""