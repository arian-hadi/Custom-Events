from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from ckeditor.fields import RichTextField


class Product(models.Model):
    """
    Product model for the shop app.
    Supports two categories: 2.0 Transformers (own products) and 1.0 Merges/Figures (external products).
    """
    
    PRODUCT_CATEGORY_CHOICES = [
        ('transformers_2_0', '2.0 Transformers Products'),
        ('merges_1_0', '1.0 Merges & Figures'),
    ]
    
    ECOMMERCE_PLATFORM_CHOICES = [
        ('amazon', 'Amazon'),
        ('aliexpress', 'AliExpress'),
        ('ebay', 'eBay'),
        ('other', 'Other'),
        ('none', 'N/A'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = RichTextField()
    category = models.CharField(
        max_length=20, 
        choices=PRODUCT_CATEGORY_CHOICES,
        default='transformers_2_0'
    )
    
    # Images
    thumbnail = models.ImageField(upload_to='shop/thumbnails/')
    main_image = models.ImageField(upload_to='shop/images/')
    
    # Pricing
    original_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    discounted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Discount Settings
    discount_active = models.BooleanField(default=False)
    
    # Free Deadline (Only for 2.0 Transformers Products)
    free_deadline = models.DateTimeField(null=True, blank=True)
    free_deadline_active = models.BooleanField(default=False)
    
    # External Link
    redirect_url = models.URLField(
        max_length=500,
        help_text="URL where users will be redirected to purchase the product"
    )
    
    # E-commerce Platform (For 1.0 Merges & Figures)
    ecommerce_platform = models.CharField(
        max_length=20,
        choices=ECOMMERCE_PLATFORM_CHOICES,
        default='none',
        help_text="Which e-commerce platform this product is from (only for 1.0 Merges & Figures)"
    )
    
    # Status and Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
    
    def __str__(self):
        return self.name
    
    def get_current_price(self):
        """Returns the current effective price based on discount and free deadline."""
        # Check if free deadline is active and product is free
        if self.is_free():
            return 0
        
        # Check if discount is active
        if self.discount_active and self.discounted_price:
            return self.discounted_price
        
        return self.original_price
    
    def is_free(self):
        """Check if product is currently free due to deadline."""
        if self.category != 'transformers_2_0':
            return False
        
        if not self.free_deadline_active or not self.free_deadline:
            return False
        
        return timezone.now() <= self.free_deadline
    
    def get_discount_percentage(self):
        """Calculate discount percentage."""
        if not self.discount_active or not self.discounted_price:
            return 0
        
        if self.original_price == 0:
            return 0
        
        discount_amount = self.original_price - self.discounted_price
        percentage = (discount_amount / self.original_price) * 100
        return round(percentage, 0)
    
    def get_discount_amount(self):
        """Calculate discount amount in dollars."""
        if not self.discount_active or not self.discounted_price:
            return 0
        return self.original_price - self.discounted_price
    
    def display_price(self):
        """Returns formatted price string."""
        if self.is_free():
            return "FREE"
        
        price = self.get_current_price()
        return f"${price:.2f}"
    
    def show_ecommerce_badge(self):
        """Determine if e-commerce platform badge should be shown."""
        return self.category == 'merges_1_0' and self.ecommerce_platform != 'none'
