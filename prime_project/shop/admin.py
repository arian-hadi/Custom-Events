from django.contrib import admin
from django.contrib import messages
from django import forms
from django_summernote.admin import SummernoteModelAdmin  # Uncomment after rebuilding container
from django_ckeditor_5.widgets import CKEditor5Widget
from django.db import models
from .models import Product, SiteLogo
from core.validators import MAX_IMAGE_FILE_SIZE_MB, validate_file_size, MAX_CHANNEL_SCREENSHOT_SIZE_MB


class ProductAdminForm(forms.ModelForm):
    """Custom form for Product admin with file size validation"""
    
    class Meta:
        model = Product
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate all image fields
        image_fields = ['thumbnail', 'main_image', 'image_2', 'image_3', 'image_4']
        
        for field_name in image_fields:
            field = cleaned_data.get(field_name)
            if field:
                try:
                    validate_file_size(field, MAX_IMAGE_FILE_SIZE_MB)
                except Exception as e:
                    self.add_error(field_name, str(e))
        
        return cleaned_data


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):  # Temporarily use ModelAdmin until container is rebuilt
    form = ProductAdminForm
    list_display = (
        'name', 
        'category', 
        'original_price', 
        'discount_active',
        'free_deadline_active',
        'ecommerce_platform',
        'is_active',
        'created_at'
    )
    list_filter = (
        'category', 
        'discount_active', 
        'free_deadline_active',
        'ecommerce_platform',
        'is_active',
        'created_at'
    )
    search_fields = ('name', 'description')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'description':
            kwargs['widget'] = CKEditor5Widget(config_name='extends')
        return super().formfield_for_dbfield(db_field, **kwargs)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'category', 'is_active')
        }),
        ('Images', {
            'fields': ('thumbnail', 'main_image', 'image_2', 'image_3', 'image_4', 'video_url'),
            'description': f"Maximum upload size for each image is {MAX_IMAGE_FILE_SIZE_MB} MB."
        }),
        ('Pricing', {
            'fields': (
                'original_price',
                'discounted_price',
                'discount_active',
            )
        }),
        ('Free Deadline (2.0 Transformers Products Only)', {
            'fields': (
                'free_deadline_active',
                'free_deadline',
            ),
            'description': 'This feature is only available for 2.0 Transformers Products. Leave empty for 1.0 Merges & Figures.'
        }),
        ('External Link', {
            'fields': ('redirect_url',)
        }),
        ('E-commerce Platform (1.0 Merges & Figures Only)', {
            'fields': ('ecommerce_platform',),
            'description': 'Specify which e-commerce platform this product is from. Only applicable for 1.0 Merges & Figures.'
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    class Media:
        js = ('admin/js/file_size_validation.js',)
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        
        # Add readonly timestamps if editing
        if obj:
            fieldsets = list(fieldsets)
            fieldsets.append(
                ('Timestamps', {
                    'fields': ('created_at', 'updated_at'),
                    'classes': ('collapse',)
                })
            )
        
        return fieldsets
    
    def save_model(self, request, obj, form, change):
        """
        Override save to validate file sizes before saving.
        """
        # Validate uploaded files from request.FILES
        image_fields = ['thumbnail', 'main_image', 'image_2', 'image_3', 'image_4']
        errors = []
        
        for field_name in image_fields:
            # Check if file was uploaded in this request
            if field_name in request.FILES:
                uploaded_file = request.FILES[field_name]
                try:
                    validate_file_size(uploaded_file, MAX_IMAGE_FILE_SIZE_MB)
                except Exception as e:
                    errors.append(f"{field_name.replace('_', ' ').title()}: {str(e)}")
            # Also check if file exists on the object (for existing files being replaced)
            elif hasattr(obj, field_name):
                field = getattr(obj, field_name, None)
                if field and hasattr(field, 'file') and field.file:
                    try:
                        validate_file_size(field, MAX_IMAGE_FILE_SIZE_MB)
                    except Exception as e:
                        errors.append(f"{field_name.replace('_', ' ').title()}: {str(e)}")
        
        if errors:
            error_message = "File size validation failed:\n" + "\n".join(f"• {error}" for error in errors)
            messages.error(request, error_message)
            # Don't save if there are errors - raise ValidationError to prevent save
            from django.core.exceptions import ValidationError
            raise ValidationError(error_message)
        
        super().save_model(request, obj, form, change)


class SiteLogoAdminForm(forms.ModelForm):
    """Custom form for SiteLogo admin with file size validation"""
    
    class Meta:
        model = SiteLogo
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate image and favicon
        if cleaned_data.get('image'):
            try:
                validate_file_size(cleaned_data['image'], MAX_CHANNEL_SCREENSHOT_SIZE_MB)
            except Exception as e:
                self.add_error('image', str(e))
        
        if cleaned_data.get('favicon'):
            try:
                validate_file_size(cleaned_data['favicon'], MAX_CHANNEL_SCREENSHOT_SIZE_MB)
            except Exception as e:
                self.add_error('favicon', str(e))
        
        return cleaned_data


@admin.register(SiteLogo)
class SiteLogoAdmin(admin.ModelAdmin):
    form = SiteLogoAdminForm
    list_display = ('name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    ordering = ('-is_active', '-created_at')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Logo Information', {
            'fields': ('name', 'image', 'is_active')
        }),
        ('Favicon', {
            'fields': ('favicon',),
            'description': 'Upload a favicon image for your site. Recommended: .ico, .png, or .svg format (32x32 or 16x16 pixels). This will appear in browser tabs.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    class Media:
        js = ('admin/js/file_size_validation.js',)
    
    def save_model(self, request, obj, form, change):
        """
        Override save to ensure only one active logo exists and validate file sizes.
        """
        # Validate image fields (using 10MB limit for logos as they might be larger)
        from core.validators import MAX_CHANNEL_SCREENSHOT_SIZE_MB
        from django.core.exceptions import ValidationError
        
        errors = []
        
        # Check uploaded files from request.FILES
        if 'image' in request.FILES:
            try:
                validate_file_size(request.FILES['image'], MAX_CHANNEL_SCREENSHOT_SIZE_MB)
            except Exception as e:
                errors.append(f"Logo image: {str(e)}")
        elif obj.image and hasattr(obj.image, 'file') and obj.image.file:
            try:
                validate_file_size(obj.image, MAX_CHANNEL_SCREENSHOT_SIZE_MB)
            except Exception as e:
                errors.append(f"Logo image: {str(e)}")
        
        if 'favicon' in request.FILES:
            try:
                validate_file_size(request.FILES['favicon'], MAX_CHANNEL_SCREENSHOT_SIZE_MB)
            except Exception as e:
                errors.append(f"Favicon: {str(e)}")
        elif obj.favicon and hasattr(obj.favicon, 'file') and obj.favicon.file:
            try:
                validate_file_size(obj.favicon, MAX_CHANNEL_SCREENSHOT_SIZE_MB)
            except Exception as e:
                errors.append(f"Favicon: {str(e)}")
        
        if errors:
            error_message = "\n".join(f"• {error}" for error in errors)
            messages.error(request, f"File size validation failed:\n{error_message}")
            raise ValidationError(error_message)
        
        if obj.is_active:
            SiteLogo.objects.filter(is_active=True).exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Highlight the active logo in the list."""
        return super().get_queryset(request)
