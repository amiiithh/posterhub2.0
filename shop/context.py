from django.core.cache import cache
from django.db.models import Avg, Count


def cart_count(request):
    cart = request.session.get("cart", {})
    return {"cart_count": sum(q for q in cart.values() if isinstance(q, int))}


def site_promos(request):
    """Real review stats and a real active coupon for the top announcement strip (cached for a minute)."""
    def build():
        from .models import Coupon, Review
        agg = Review.objects.filter(is_approved=True).aggregate(n=Count("id"), avg=Avg("rating"))
        promo = next(
            (c for c in Coupon.objects.filter(active=True).order_by("-first_order_only", "-value") if c.is_available()),
            None,
        )
        return {"site_rating": agg if agg["n"] else None, "promo_coupon": promo}
    return cache.get_or_set("site_promos", build, 60)
