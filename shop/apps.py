from django.apps import AppConfig


class ShopConfig(AppConfig):
    name = "shop"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .cart import on_login

        user_logged_in.connect(on_login, dispatch_uid="shop_merge_session_cart")
