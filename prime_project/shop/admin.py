from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin  # Uncomment after rebuilding container
from django_ckeditor_5.widgets import CKEditor5Widget
from django.db import models
from .models import Product, SiteLogo


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):  # Temporarily use ModelAdmin until container is rebuilt
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
            'fields': ('thumbnail', 'main_image', 'video_url')
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


@admin.register(SiteLogo)
class SiteLogoAdmin(admin.ModelAdmin):
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
    
    def save_model(self, request, obj, form, change):
        """
        Override save to ensure only one active logo exists.
        This is handled in the model's save method, but we ensure it here too.
        """
        if obj.is_active:
            SiteLogo.objects.filter(is_active=True).exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Highlight the active logo in the list."""
        return super().get_queryset(request)
