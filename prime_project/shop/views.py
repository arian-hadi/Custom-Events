from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
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
    
    # Check which products are favorited by the user
    favorited_product_ids = []
    if request.user.is_authenticated:
        favorited_product_ids = list(
            request.user.favorite_products.filter(is_active=True).values_list('id', flat=True)
        )
    
    context = {
        'products': products,
        'category_filter': category_filter,
        'search_query': search_query,
        'transformers_count': transformers_count,
        'merges_count': merges_count,
        'favorited_product_ids': favorited_product_ids,
    }
    
    return render(request, 'shop/product_list.html', context)


def product_detail(request, product_id):
    """Display detailed view of a single product."""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Check if product is favorited by the user
    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = product.favorites.filter(id=request.user.id).exists()
    
    # Get related products (same category)
    related_products = Product.objects.filter(
        category=product.category,
        is_active=True
    ).exclude(id=product.id)[:4]
    
    context = {
        'product': product,
        'related_products': related_products,
        'is_favorited': is_favorited,
    }
    
    return render(request, 'shop/product_detail.html', context)


@login_required
@require_POST
def toggle_favorite(request, product_id):
    """Toggle favorite status for a product (AJAX endpoint)."""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    if product.favorites.filter(id=request.user.id).exists():
        # Remove from favorites
        product.favorites.remove(request.user)
        is_favorited = False
    else:
        # Add to favorites
        product.favorites.add(request.user)
        is_favorited = True
    
    return JsonResponse({
        'success': True,
        'is_favorited': is_favorited,
        'message': 'Added to favorites' if is_favorited else 'Removed from favorites'
    })


@login_required
def favorites_list(request):
    """Display list of user's favorite products."""
    favorites_qs = request.user.favorite_products.filter(is_active=True).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(favorites_qs, 12)
    page = request.GET.get('page')
    favorites = paginator.get_page(page)
    
    # Get product IDs from the current page
    favorited_product_ids = [product.id for product in favorites]
    
    context = {
        'favorites': favorites,
        'favorited_product_ids': favorited_product_ids,
    }
    
    return render(request, 'shop/favorites_list.html', context)
