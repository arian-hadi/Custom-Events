from django import forms
from .models import Event, EventApplication

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'deadline', 'date']  # <-- Add 'date'
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'date': forms.DateInput(attrs={'type': 'date'}),  # <-- Add this line too
            'description': forms.Textarea(attrs={'rows': 4}),
        }
class EventApplicationForm(forms.ModelForm):
    """Form for members to apply for an event dynamically."""
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

        if event:
            for field in event.custom_fields.all():
                field_name = f"field_{field.id}"

                if field.field_type == 'text':
                    self.fields[field_name] = forms.CharField(label=field.name, required=True)
                elif field.field_type == 'number':
                    self.fields[field_name] = forms.FloatField(label=field.name, required=True)
                elif field.field_type == 'date':
                    self.fields[field_name] = forms.DateField(label=field.name, widget=forms.DateInput(attrs={'type': 'date'}))
                elif field.field_type == 'boolean':
                    self.fields[field_name] = forms.BooleanField(label=field.name, required=False)

    class Meta:
        model = EventApplication
        fields = []  # Keep it empty since fields are dynamically generated


class EventSearchForm(forms.Form):
    """Search form for filtering events."""
    search = forms.CharField(required=False, widget=forms.TextInput(
        attrs={'placeholder': 'Event title or keyword'}
    ))
