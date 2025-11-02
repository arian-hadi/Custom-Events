from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from .models import Product


def product_list(request):
    """Display list of all active products with filtering by category."""
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    
    products = Product.objects.filter(is_active=True)
    
    # Filter by category
    if category_filter:
        products = products.filter(category=category_filter)
    
    # Search functionality
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(products, 12)  # Show 12 products per page
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    # Category counts for filter display
    transformers_count = Product.objects.filter(
        is_active=True, 
        category='transformers_2_0'
    ).count()
    merges_count = Product.objects.filter(
        is_active=True, 
        category='merges_1_0'
    ).count()
    
    context = {
        'products': products,
        'category_filter': category_filter,
        'search_query': search_query,
        'transformers_count': transformers_count,
        'merges_count': merges_count,
    }
    
    return render(request, 'shop/product_list.html', context)


def product_detail(request, product_id):
    """Display detailed view of a single product."""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Get related products (same category)
    related_products = Product.objects.filter(
        category=product.category,
        is_active=True
    ).exclude(id=product.id)[:4]
    
    context = {
        'product': product,
        'related_products': related_products,
    }
    
    return render(request, 'shop/product_detail.html', context)
