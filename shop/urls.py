from django.urls import path
from . import views as v
from . import views_admin as va

urlpatterns = [
    # ── Storefront ─────────────────────────────────────────────────────────────
    path("", v.home, name="home"),
    path("poster/<int:pk>/", v.detail, name="detail"),
    path("cart/", v.cart, name="cart"),
    path("cart/add/", v.cart_add, name="cart_add"),
    path("cart/update/", v.cart_update, name="cart_update"),
    path("checkout/", v.checkout, name="checkout"),
    path("orders/", v.orders, name="orders"),
    path("orders/<int:pk>/invoice/", v.invoice, name="invoice"),
    path("orders/<int:pk>/cancel/", v.cancel, name="cancel"),
    path("wishlist/", v.wishlist, name="wishlist"),
    path("wishlist/toggle/<int:pk>/", v.wish_toggle, name="wish_toggle"),
    path("review/<int:pk>/like/", v.review_like, name="review_like"),
    path("register/", v.register, name="register"),
    path("profile/", v.profile, name="profile"),

    # ── Admin: dashboard & orders ──────────────────────────────────────────────
    # Prefixed "manage/" so Django's own /admin/ catch-all doesn't shadow these.
    path("manage/dashboard/", va.admin_dashboard, name="admin_dashboard"),
    path("manage/orders/", va.admin_orders, name="admin_orders"),
    path("manage/orders/<int:pk>/", va.admin_order_detail, name="admin_order_detail"),

    # ── Admin: posters ─────────────────────────────────────────────────────────
    path("manage/posters/", va.admin_posters, name="admin_posters"),
    path("manage/posters/<int:pk>/edit/", va.admin_poster_edit, name="admin_poster_edit"),
    path("manage/posters/<int:pk>/delete/", va.admin_poster_delete, name="admin_poster_delete"),

    # ── Admin: categories ──────────────────────────────────────────────────────
    path("manage/categories/", va.admin_categories, name="admin_categories"),
    path("manage/categories/<int:pk>/edit/", va.admin_category_edit, name="admin_category_edit"),

    # ── Admin: coupons ─────────────────────────────────────────────────────────
    path("manage/coupons/", va.admin_coupons, name="admin_coupons"),
    path("manage/coupons/<int:pk>/edit/", va.admin_coupon_edit, name="admin_coupon_edit"),

    # ── Admin: users & reviews ─────────────────────────────────────────────────
    path("manage/users/", va.admin_users, name="admin_users"),
    path("manage/reviews/", va.admin_reviews, name="admin_reviews"),
]
