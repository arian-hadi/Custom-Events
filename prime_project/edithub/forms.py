from django import forms
from .models import EditorApplication, EditSubmission, EditReport
from .utils import validate_channel_url


class EditorApplicationForm(forms.ModelForm):
    """Form for submitting editor applications"""

    channel_type = forms.ChoiceField(
        choices=EditorApplication.CHANNEL_TYPE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'flex flex-col sm:flex-row gap-3'}),
        required=True,
        label="Select Platform"
    )

    editing_tool = forms.ChoiceField(
        choices=EditorApplication.EDITING_TOOL_CHOICES,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
        }),
        required=True,
        label="Primary Editing Software"
    )

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
                  'editing_tool', 'channel_screenshot', 'channel_verified', 'data_consent']
        widgets = {
            'channel_link': forms.URLInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'placeholder': 'https://www.youtube.com/@channelname or https://www.tiktok.com/@username'
            }),
            'editing_area': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['channel_link'].required = True
        self.fields['editing_area'].required = True
        
        if not self.data:
            self.initial.setdefault('channel_type', 'youtube')
            self.initial.setdefault('editing_tool', 'after_effects')

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
        
        # Ensure provided platform matches URL
        selected_channel_type = self.cleaned_data.get('channel_type') or self.data.get('channel_type')
        if selected_channel_type and selected_channel_type != channel_type:
            raise forms.ValidationError(
                f"The provided URL appears to be for {channel_type.title()} but you selected {selected_channel_type.title()}."
            )
        
        # Set channel_type in cleaned_data for view usage
        self.cleaned_data['channel_type'] = channel_type
        
        return channel_link
    
    def clean(self):
        cleaned_data = super().clean()
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


class EditSubmissionForm(forms.ModelForm):
    """Form for submitting edits for Edit of the Week"""
    
    class Meta:
        model = EditSubmission
        fields = ['video_url', 'title', 'description']
        widgets = {
            'video_url': forms.URLInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'placeholder': 'https://www.youtube.com/shorts/... or https://www.tiktok.com/@username/video/...'
            }),
            'title': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'placeholder': 'Edit title (optional)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Description (optional)'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.approved_application = kwargs.pop('approved_application', None)
        super().__init__(*args, **kwargs)
        self.fields['video_url'].required = True
    
    def clean_video_url(self):
        video_url = self.cleaned_data.get('video_url')
        if not video_url:
            raise forms.ValidationError('Video URL is required')
        
        if not self.approved_application:
            raise forms.ValidationError('No approved application found. Please apply and get approved first.')
        
        # Verify video belongs to the approved channel
        from .utils import verify_video_belongs_to_channel
        is_valid, error_message = verify_video_belongs_to_channel(
            video_url,
            self.approved_application.channel_link,
            self.approved_application.channel_type
        )
        
        if not is_valid:
            raise forms.ValidationError(error_message or 'Video does not belong to your approved channel')
        
        return video_url


class EditReportForm(forms.ModelForm):
    """Form for reporting edits"""
    
    class Meta:
        model = EditReport
        fields = ['reason', 'description']
        widgets = {
            'reason': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
            }),
            'description': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Additional details (optional)'
            }),
        }
    

