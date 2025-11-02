from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name',
            'description',
            'category',
            'thumbnail',
            'main_image',
            'original_price',
            'discounted_price',
            'discount_active',
            'free_deadline',
            'free_deadline_active',
            'redirect_url',
            'ecommerce_platform',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Product Name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'rows': 5,
                'placeholder': 'Product Description'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
            }),
            'original_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'step': '0.01',
                'min': '0'
            }),
            'discounted_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'step': '0.01',
                'min': '0'
            }),
            'discount_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
            }),
            'free_deadline': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'type': 'datetime-local'
            }),
            'free_deadline_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
            }),
            'redirect_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'https://example.com/product'
            }),
            'ecommerce_platform': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        free_deadline_active = cleaned_data.get('free_deadline_active')
        free_deadline = cleaned_data.get('free_deadline')
        ecommerce_platform = cleaned_data.get('ecommerce_platform')
        
        # Validate free deadline is only for 2.0 Transformers products
        if category == 'merges_1_0' and free_deadline_active:
            raise forms.ValidationError({
                'free_deadline_active': 'Free deadline feature is only available for 2.0 Transformers Products.'
            })
        
        if category == 'merges_1_0' and free_deadline:
            raise forms.ValidationError({
                'free_deadline': 'Free deadline feature is only available for 2.0 Transformers Products.'
            })
        
        # Validate ecommerce platform is set for 1.0 products
        if category == 'merges_1_0' and ecommerce_platform == 'none':
            raise forms.ValidationError({
                'ecommerce_platform': 'Please specify the e-commerce platform for 1.0 Merges & Figures products.'
            })
        
        # Validate discount
        discount_active = cleaned_data.get('discount_active')
        discounted_price = cleaned_data.get('discounted_price')
        
        if discount_active and not discounted_price:
            raise forms.ValidationError({
                'discounted_price': 'Discounted price is required when discount is active.'
            })
        
        original_price = cleaned_data.get('original_price')
        if discount_active and discounted_price and original_price:
            if discounted_price >= original_price:
                raise forms.ValidationError({
                    'discounted_price': 'Discounted price must be less than original price.'
                })
        
        return cleaned_data


