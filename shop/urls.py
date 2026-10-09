from django.urls import path
from . import views as v
from . import views_admin as va

urlpatterns = [
    path("", v.home, name="home"), path("poster/<int:pk>/", v.detail, name="detail"),
    path("cart/", v.cart, name="cart"), path("cart/add/", v.cart_add, name="cart_add"),
    path("cart/update/", v.cart_update, name="cart_update"),
    path("checkout/", v.checkout, name="checkout"), path("orders/", v.orders, name="orders"),
    path("orders/<int:pk>/cancel/", v.cancel, name="cancel"),
    path("wishlist/", v.wishlist, name="wishlist"), path("wishlist/toggle/<int:pk>/", v.wish_toggle, name="wish_toggle"),
    path("register/", v.register, name="register"),
    path("profile/", v.profile, name="profile"),
    # ── admin ──────────────────────────────────────────────────────────────────
    # Prefixed "manage/" (not "admin/") so Django's own admin catch-all doesn't shadow these.
    path("manage/posters/", va.admin_posters, name="admin_posters"),
    path("manage/posters/<int:pk>/edit/", va.admin_poster_edit, name="admin_poster_edit"),
    path("manage/orders/", va.admin_orders, name="admin_orders"),
    path("manage/orders/<int:pk>/", va.admin_order_detail, name="admin_order_detail"),
    path("manage/dashboard/", va.admin_dashboard, name="admin_dashboard"),
]
