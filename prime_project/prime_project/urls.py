
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from core.views import HomeView


urlpatterns = [
    path('legacy/', HomeView.as_view()),
    path('api/v2/auth/', include('accounts.api_urls')),
    path('api/v2/email/', include('notifications.campaign_urls')),
    path('api/v2/payments/', include('shop.payment_urls')),
    path('api/v2/', include('platform_api.urls')),
    path('admin/', admin.site.urls),
    path('summernote/', include('django_summernote.urls')),  # Uncomment after rebuilding container
    path("ckeditor5/", include('django_ckeditor_5.urls')),
    path('contact/', include('contact.urls')),
    path('',include('core.urls')),
    path('events/', include('events.urls')),
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),
    path('accounts/', include('accounts.urls')),
    path('announcements/', include('announcements.urls')),
    path('shop/', include('shop.urls', namespace='shop')),
    path('editinghub/', include('edithub.urls', namespace='edithub')),
    path('notifications/', include('notifications.urls', namespace='notifications')),
  
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
