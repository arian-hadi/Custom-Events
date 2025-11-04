from django import forms
from .models import EditorApplication
from .utils import validate_channel_url


class EditorApplicationForm(forms.ModelForm):
    """Form for submitting editor applications"""
    
    editing_area_other = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
            'placeholder': 'Specify your editing area'
        }),
        help_text="Required if 'Others' is selected"
    )
    
    channel_screenshot = forms.ImageField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100',
            'accept': 'image/*'
        }),
        help_text="Upload a screenshot of your channel page to verify ownership (no need to show email address)"
    )
    
    channel_verified = forms.BooleanField(
        required=False,  # Will be set on confirmation page
        widget=forms.HiddenInput()
    )
    
    data_consent = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-blue-600 focus:ring-blue-500'
        }),
        label="I consent to my data being displayed on this website and confirm it will not be used for any misuse"
    )
    
    class Meta:
        model = EditorApplication
        fields = ['channel_link', 'channel_type', 'editing_area', 'editing_area_other', 
                  'channel_screenshot', 'channel_verified', 'data_consent']
        widgets = {
            'channel_link': forms.URLInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'placeholder': 'https://www.youtube.com/@channelname or https://www.tiktok.com/@username'
            }),
            'channel_type': forms.HiddenInput(attrs={'value': ''}),  # Will be set automatically
            'editing_area': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['channel_link'].required = True
        self.fields['editing_area'].required = True
        # channel_type is set automatically from channel_link, so it's not required in the form
        self.fields['channel_type'].required = False
        
        # Make editing_area_other required if editing_area is 'others'
        if self.data and 'editing_area' in self.data:
            editing_area = self.data.get('editing_area')
            if editing_area == 'others':
                self.fields['editing_area_other'].required = True
    
    def clean_channel_link(self):
        channel_link = self.cleaned_data.get('channel_link')
        if not channel_link:
            raise forms.ValidationError('Channel link is required')
        
        # Validate URL format
        is_valid, channel_type, error_message = validate_channel_url(channel_link)
        if not is_valid:
            raise forms.ValidationError(error_message or 'Invalid channel URL')
        
        # Set channel_type in cleaned_data - this will be used by clean()
        self.cleaned_data['channel_type'] = channel_type
        
        # Check if user already has an application with this channel
        # Note: We need to check this in the view since we don't have user in form context
        # This check is moved to the view to avoid issues
        
        return channel_link
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Ensure channel_type is set from channel_link validation
        if 'channel_link' in cleaned_data and 'channel_type' not in cleaned_data:
            channel_link = cleaned_data['channel_link']
            is_valid, channel_type, _ = validate_channel_url(channel_link)
            if is_valid:
                cleaned_data['channel_type'] = channel_type
        
        editing_area = cleaned_data.get('editing_area')
        editing_area_other = cleaned_data.get('editing_area_other')
        
        # Validate editing_area_other is provided if editing_area is 'others'
        if editing_area == 'others' and not editing_area_other:
            raise forms.ValidationError({
                'editing_area_other': 'Please specify your editing area'
            })
        
        # Validate data_consent
        if not cleaned_data.get('data_consent'):
            raise forms.ValidationError({
                'data_consent': 'You must consent to data usage to proceed'
            })
        
        # channel_verified will be set on confirmation page, not here
        return cleaned_data
    

