from django.urls import path
from . import payment_views

app_name = "payments"
urlpatterns = [
    path("checkout/", payment_views.checkout, name="checkout"),
    path("orders/", payment_views.orders, name="orders"),
    path("orders/<uuid:order_id>/", payment_views.order_detail, name="order-detail"),
    path("stripe/webhook/", payment_views.stripe_webhook, name="stripe-webhook"),
]
