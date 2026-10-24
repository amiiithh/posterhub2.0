"""The Vault (cart): saved to the account when signed in, kept in the browser session before that."""
from django.db import transaction
from django.db.models import F

from .models import MAX_CART_QTY, SIZES, CartItem, Poster


def _clean_session(raw):
    """Keep only well-formed lines from the browser's cart: {'<poster_id>:<size>': qty}."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for key, qty in raw.items():
        pid, _, size = str(key).partition(":")
        if pid.isdigit() and size in SIZES and isinstance(qty, int) and qty > 0:
            out[f"{int(pid)}:{size}"] = min(qty, MAX_CART_QTY)
    return out


class Cart:
    def __init__(self, request):
        self.request = request
        self.user = request.user if request.user.is_authenticated else None
        if self.user and request.session.get("cart"):
            merge_session_cart(request, self.user)   # e.g. items left in the session from before the upgrade

    def lines(self):
        """{'<poster_id>:<size>': qty} for the current visitor."""
        if self.user:
            rows = CartItem.objects.filter(user=self.user).order_by("created", "pk").values_list("poster_id", "size", "qty")
            return {f"{p}:{s}": q for p, s, q in rows}
        return _clean_session(self.request.session.get("cart", {}))

    def count(self):
        """Number of items that will actually appear in the cart (hidden posters are ignored)."""
        lines = self.lines()
        if not lines:
            return 0
        ids = {int(k.partition(":")[0]) for k in lines}
        live = set(Poster.objects.filter(pk__in=ids, is_active=True).values_list("pk", flat=True))
        return sum(q for k, q in lines.items() if int(k.partition(":")[0]) in live)

    def add(self, poster_id, size):
        """Add one copy. Returns False when the line is already at the maximum."""
        if self.user:
            item, created = CartItem.objects.get_or_create(user=self.user, poster_id=poster_id, size=size)
            if created:
                return True
            if item.qty >= MAX_CART_QTY:
                return False
            CartItem.objects.filter(pk=item.pk).update(qty=F("qty") + 1)
            return True
        cart = _clean_session(self.request.session.get("cart", {}))
        key = f"{poster_id}:{size}"
        if cart.get(key, 0) >= MAX_CART_QTY:
            return False
        cart[key] = cart.get(key, 0) + 1
        self.request.session["cart"] = cart
        return True

    def update(self, key, action):
        """action is 'inc', 'dec' or 'del'. Unknown lines are ignored."""
        pid, _, size = str(key).partition(":")
        if not (pid.isdigit() and size in SIZES):
            return
        if self.user:
            with transaction.atomic():
                item = CartItem.objects.select_for_update().filter(user=self.user, poster_id=int(pid), size=size).first()
                if not item:
                    return
                new = min(MAX_CART_QTY, {"inc": item.qty + 1, "dec": item.qty - 1}.get(action, 0))
                if new < 1:
                    item.delete()
                else:
                    item.qty = new
                    item.save(update_fields=["qty", "updated"])
            return
        cart = _clean_session(self.request.session.get("cart", {}))
        key = f"{int(pid)}:{size}"
        if key not in cart:
            return
        new = min(MAX_CART_QTY, {"inc": cart[key] + 1, "dec": cart[key] - 1}.get(action, 0))
        if new < 1:
            del cart[key]
        else:
            cart[key] = new
        self.request.session["cart"] = cart

    def clear(self):
        if self.user:
            CartItem.objects.filter(user=self.user).delete()
        else:
            self.request.session["cart"] = {}


def merge_session_cart(request, user):
    """On sign-in, fold what the visitor added before signing in into their saved Vault."""
    lines = _clean_session(request.session.get("cart", {}))
    request.session.pop("cart", None)
    if not lines:
        return
    live = set(Poster.objects.filter(pk__in={int(k.partition(":")[0]) for k in lines}, is_active=True).values_list("pk", flat=True))
    with transaction.atomic():
        for key, qty in lines.items():
            pid, _, size = key.partition(":")
            if int(pid) not in live:
                continue
            item, created = CartItem.objects.get_or_create(user=user, poster_id=int(pid), size=size, defaults={"qty": qty})
            if not created:
                item.qty = min(MAX_CART_QTY, item.qty + qty)
                item.save(update_fields=["qty", "updated"])


def on_login(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        merge_session_cart(request, user)
