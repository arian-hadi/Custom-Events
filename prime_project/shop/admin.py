from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
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
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'category', 'is_active')
        }),
        ('Images', {
            'fields': ('thumbnail', 'main_image')
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
