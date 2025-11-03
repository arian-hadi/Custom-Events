from django.urls import path
from . import views

app_name = 'shop'

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('favorites/', views.favorites_list, name='favorites_list'),
    path('<int:product_id>/', views.product_detail, name='product_detail'),
    path('<int:product_id>/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
]


