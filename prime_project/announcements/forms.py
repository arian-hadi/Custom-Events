# announcements/forms.py

from django import forms
from .models import Announcement

class AnnouncementAdminForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = '__all__'
        widgets = {
            'message': forms.Textarea(attrs={'rows': 5}),
        }
