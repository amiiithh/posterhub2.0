from django.urls import path
from . import views as v
urlpatterns = [
    path("", v.home, name="home"), path("poster/<int:pk>/", v.detail, name="detail"),
    path("cart/", v.cart, name="cart"), path("cart/add/", v.cart_add, name="cart_add"),
    path("cart/update/", v.cart_update, name="cart_update"),
    path("checkout/", v.checkout, name="checkout"), path("orders/", v.orders, name="orders"),
    path("orders/<int:pk>/cancel/", v.cancel, name="cancel"),
    path("wishlist/", v.wishlist, name="wishlist"), path("wishlist/toggle/<int:pk>/", v.wish_toggle, name="wish_toggle"),
    path("register/", v.register, name="register"),
]
