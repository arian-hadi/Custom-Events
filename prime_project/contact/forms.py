from django import forms

class ContactForm(forms.Form):
    subject = forms.CharField(max_length =150)   
    email = forms.EmailField(max_length=150)
    message = forms.CharField(widget=forms.Textarea)

