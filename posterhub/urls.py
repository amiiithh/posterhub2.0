from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from shop.views import cart_preserving_logout

urlpatterns = [
    path("admin/", admin.site.urls),
    # Override Django's default logout to preserve the cart across session flush
    path("accounts/logout/", cart_preserving_logout, name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("shop.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
