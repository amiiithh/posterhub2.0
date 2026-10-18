from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.mail import send_mail
from django.db.models import Avg, Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .models import *

def home(request):
    q, cat, sort = request.GET.get("q", ""), request.GET.get("cat", ""), request.GET.get("sort", "")
    ps = Poster.objects.filter(is_active=True).annotate(avg=Avg("reviews__rating"))
    if q: ps = ps.filter(Q(title__icontains=q) | Q(artist__icontains=q) | Q(description__icontains=q))
    if cat: ps = ps.filter(category__slug=cat)
    ps = ps.order_by({"lo": "base_price", "hi": "-base_price"}.get(sort, "-created"))
    craftsmanship = [
        ("fa-solid fa-scroll", "300 GSM Archival Velvet", "Heavy museum-grade Fuji matte pulp. Zero glare, zero reflection under spotlighting."),
        ("fa-solid fa-droplet", "12-Color Giclée Glaze", "Lucia Pro archival pigment inks yielding 100+ year colour fidelity and deep obsidian blacks."),
        ("fa-solid fa-hand-holding-hand", "Zero-Damage Nano Tabs", "Industrial micro-suction strips peel cleanly off delicate Indian wall putty without peeling paint."),
        ("fa-solid fa-box-archive", "Reinforced Tube Pack", "Double-wall rigid spiral cylinders with moisture barrier parchment for weather immunity."),
    ]
    top_reviews = list(
        Review.objects.filter(is_approved=True)
        .select_related("poster", "user", "user__profile")
        .annotate(
            like_count=Count("likes", distinct=True),
            verified=Exists(OrderItem.objects.filter(
                poster=OuterRef("poster"), order__user=OuterRef("user")
            ).exclude(order__status="Cancelled")),
        )
        .order_by("-like_count", "-rating", "-created")[:3]
    )
    liked_ids = set(request.user.liked_reviews.values_list("pk", flat=True)) if request.user.is_authenticated else set()
    agg = Review.objects.filter(is_approved=True).aggregate(n=Count("id"), avg=Avg("rating"))
    review_stats = {"n": agg["n"], "avg": agg["avg"],
                    "stars": [i <= round(agg["avg"] or 0) for i in range(1, 6)]}
    ranked = (Poster.objects.filter(is_active=True)
              .annotate(sold=Coalesce(Sum("order_items__qty", filter=~Q(order_items__order__status="Cancelled")), 0))
              .order_by("-sold", "-created"))
    top = list(ranked[:7])  # best sellers first, topped up with the newest posters
    bestseller_ids = {p.pk for p in top[:2] if p.sold > 0}
    # Arrange so the #1 seller sits in the centre of the deck, the rest fanning out beside it
    deck, mid, k, i = [None] * len(top), len(top) // 2, 0, 0
    while i < len(top):
        for pos in ((mid,) if k == 0 else (mid + k, mid - k)):
            if 0 <= pos < len(top) and i < len(top) and deck[pos] is None:
                deck[pos] = top[i]; i += 1
        k += 1
    return render(request, "home.html", {
        "posters": ps, "deck": deck, "bestseller_ids": bestseller_ids, "cats": Category.objects.all(),
        "q": q, "cat": cat, "sort": sort,
        "craftsmanship": craftsmanship,
        "top_reviews": top_reviews, "liked_ids": liked_ids, "review_stats": review_stats,
    })

def detail(request, pk):
    p = get_object_or_404(Poster, pk=pk)
    can_review = request.user.is_authenticated and not Review.objects.filter(
        user=request.user, poster=p).exists() and OrderItem.objects.filter(
        poster=p, order__user=request.user).exclude(order__status="Cancelled").exists()
    if request.method == "POST" and can_review:
        Review.objects.get_or_create(poster=p, user=request.user, defaults={
            "rating": int(request.POST.get("rating", 5)),
            "text": request.POST.get("text", ""),
        })
        messages.success(request, "Review posted.")
        return redirect("detail", pk=pk)
    wished = request.user.is_authenticated and Wishlist.objects.filter(user=request.user, poster=p).exists()
    specs = [
        ("Paper", "300 GSM Archival Velvet Matte"),
        ("Ink", "12-Color Giclée Pigment"),
        ("Mounting", "16x Nano-Adhesive Tabs"),
        ("Dispatch", "Crush-Proof Tube Pack"),
        ("Sizes", "A4 · A3 · A2"),
        ("Category", str(p.category)),
    ]
    avg_val = p.reviews.filter(is_approved=True).aggregate(a=Avg("rating"))["a"]
    reviews = p.reviews.filter(is_approved=True).select_related("user").annotate(
        like_count=Count("likes")).order_by("-like_count", "-created")
    liked_ids = set(request.user.liked_reviews.values_list("pk", flat=True)) if request.user.is_authenticated else set()
    return render(request, "detail.html", {
        "p": p,
        "sizes": [(s, p.price(s)) for s in SIZES],
        "can_review": can_review,
        "wished": wished,
        "reviews": reviews, "liked_ids": liked_ids,
        "avg": avg_val,
        "avg_int": round(avg_val) if avg_val else 0,
        "specs": specs,
    })

def _cart(request):
    items, total = [], 0
    for k, q in request.session.get("cart", {}).items():
        pid, size = k.split(":"); p = Poster.objects.filter(pk=pid).first()
        if p:
            pr = p.price(size); items.append({"key": k, "poster": p, "size": size, "qty": q, "price": pr, "sub": pr * q}); total += pr * q
    return items, total

def cart(request):
    items, total = _cart(request); return render(request, "cart.html", {"items": items, "total": total})

@require_POST
def cart_add(request):
    size = request.POST.get("size", "A4")
    if size not in SIZES: size = "A4"
    c = request.session.get("cart", {}); k = f"{get_object_or_404(Poster, pk=request.POST['poster']).pk}:{size}"
    c[k] = c.get(k, 0) + 1; request.session["cart"] = c; messages.success(request, "Added to cart."); return redirect("cart")

@require_POST
def cart_update(request):
    c = request.session.get("cart", {}); k, a = request.POST["key"], request.POST["action"]
    if k in c:
        c[k] += {"inc": 1, "dec": -1}.get(a, -c[k])
        if c[k] < 1: del c[k]
    request.session["cart"] = c; return redirect("cart")

@login_required
def checkout(request):
    items, total = _cart(request)
    if not items: return redirect("cart")

    # ── Coupon logic ─────────────────────────────────────────────────────────
    coupon = None
    discount = 0
    coupon_msg = ""
    coupon_code = request.session.get("coupon_code", "")

    if request.method == "POST" and request.POST.get("action") == "apply_coupon":
        code = request.POST.get("coupon_code", "").strip().upper()
        try:
            c = Coupon.objects.get(code=code)
            if c.is_available():
                disc = c.apply(total)
                if total < c.min_total:
                    messages.error(request, f"Minimum order of ₹{c.min_total} required for '{code}'.")
                elif disc == 0:
                    messages.error(request, f"Coupon '{code}' gives ₹0 discount on your cart.")
                else:
                    request.session["coupon_code"] = code
                    messages.success(request, f"Coupon '{code}' applied — you save ₹{disc}!")
            else:
                messages.error(request, f"Coupon '{code}' is expired or unavailable.")
        except Coupon.DoesNotExist:
            messages.error(request, f"Coupon '{code}' not found.")
        return redirect("checkout")

    if request.method == "POST" and request.POST.get("action") == "remove_coupon":
        request.session.pop("coupon_code", None)
        messages.info(request, "Coupon removed.")
        return redirect("checkout")

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code)
            if coupon.is_available():
                discount = coupon.apply(total)
            else:
                # coupon expired between apply and checkout — silently drop it
                request.session.pop("coupon_code", None)
                coupon = None
                discount = 0
        except Coupon.DoesNotExist:
            request.session.pop("coupon_code", None)
            coupon = None

    final_total = max(0, total - discount)

    if request.method == "POST" and request.POST.get("action") == "place_order":
        o = Order.objects.create(
            user=request.user,
            name=request.POST["name"],
            address=request.POST["address"],
            phone=request.POST["phone"],
            payment=request.POST["payment"],
            total=final_total,
            coupon_code=coupon.code if coupon else "",
            discount_amount=discount,
        )
        for i in items: OrderItem.objects.create(order=o, poster=i["poster"], size=i["size"], qty=i["qty"], price=i["price"])
        if coupon:
            coupon.times_used += 1
            coupon.save(update_fields=["times_used"])
        request.session["cart"] = {}
        request.session.pop("coupon_code", None)
        send_mail(
            f"PosterHub order #{o.pk} confirmed",
            f"Thanks {o.name}! Your order of ₹{final_total} is being processed.",
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email or "noreply@posterhub.com"],
        )
        messages.success(request, f"Order #{o.pk} placed successfully!")
        return redirect("orders")

    return render(request, "checkout.html", {
        "items": items,
        "total": total,
        "coupon": coupon,
        "discount": discount,
        "final_total": final_total,
    })

@login_required
def orders(request):
    return render(request, "orders.html", {"orders": request.user.orders.prefetch_related("items__poster").order_by("-created")})

@login_required
@require_POST
def cancel(request, pk):
    o = get_object_or_404(Order, pk=pk, user=request.user)
    if o.status == "Processing": o.status = "Cancelled"; o.save(); messages.info(request, "Order cancelled.")
    return redirect("orders")

@login_required
def wishlist(request):
    return render(request, "wishlist.html", {"posters": Poster.objects.filter(wishlist__user=request.user).annotate(avg=Avg("reviews__rating"))})

@login_required
@require_POST
def wish_toggle(request, pk):
    w, made = Wishlist.objects.get_or_create(user=request.user, poster_id=pk)
    if made:
        messages.success(request, "Saved to wishlist.")
    else:
        w.delete(); messages.info(request, "Removed from wishlist.")
    nxt = request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect("detail", pk=pk)

def register(request):
    f = UserCreationForm(request.POST or None)
    if request.method == "POST" and f.is_valid():
        user = f.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("home")
    return render(request, "registration/register.html", {"form": f})


@require_POST
def cart_preserving_logout(request):
    """Logout while keeping the cart and coupon in the new (anonymous) session."""
    cart = request.session.get("cart", {})
    coupon_code = request.session.get("coupon_code", "")
    auth_logout(request)          # flushes session, creates a fresh one
    if cart:
        request.session["cart"] = cart
    if coupon_code:
        request.session["coupon_code"] = coupon_code
    return redirect(settings.LOGOUT_REDIRECT_URL or "/")

@login_required
def profile(request):
    prof, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        prof.phone = request.POST.get("phone", prof.phone)[:20]
        prof.address = request.POST.get("address", prof.address)
        prof.city = request.POST.get("city", prof.city)[:60]
        prof.state = request.POST.get("state", prof.state)[:60]
        prof.pincode = request.POST.get("pincode", prof.pincode)[:10]
        prof.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    orders = request.user.orders.prefetch_related("items__poster").order_by("-created")
    all_orders = list(orders)
    stats = {
        "orders": len(all_orders),
        "spent": sum(o.total for o in all_orders if o.status != "Cancelled"),
        "wishlist": Wishlist.objects.filter(user=request.user).count(),
        "reviews": Review.objects.filter(user=request.user).count(),
    }
    coupons = [c for c in Coupon.objects.order_by("-value") if c.is_available()]
    return render(request, "profile.html", {
        "prof": prof,
        "stats": stats,
        "coupons": coupons,
        "recent_orders": all_orders[:5],
        "order_count": len(all_orders),
    })


@require_POST
@login_required
def review_like(request, pk):
    r = get_object_or_404(Review, pk=pk, is_approved=True)
    if r.user_id == request.user.id:
        messages.info(request, "You can't like your own review.")
    elif r.likes.filter(pk=request.user.pk).exists():
        r.likes.remove(request.user)
    else:
        r.likes.add(request.user)
    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/#reviews"
    return redirect(nxt)