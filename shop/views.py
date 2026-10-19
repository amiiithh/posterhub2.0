from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.decorators import login_required
import logging
from urllib.parse import urlencode

from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Exists, F, OuterRef, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import CartAddForm, CartUpdateForm, CheckoutForm, RegisterForm, ReviewForm
from .models import *

log = logging.getLogger(__name__)
MAX_QTY = 20          # most copies of one poster+size in a cart
HOME_PAGE_SIZE = 12   # posters per page on the home page
APPROVED_AVG = Avg("reviews__rating", filter=Q(reviews__is_approved=True))

def home(request):
    q, cat, sort = request.GET.get("q", ""), request.GET.get("cat", ""), request.GET.get("sort", "")
    ps = Poster.objects.filter(is_active=True).select_related("category").annotate(avg=APPROVED_AVG)
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
              .select_related("category")
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
    page_obj = Paginator(ps, HOME_PAGE_SIZE).get_page(request.GET.get("page"))
    page_qs = urlencode({k: x for k, x in (("q", q), ("cat", cat), ("sort", sort)) if x})
    return render(request, "home.html", {
        "posters": page_obj, "page_obj": page_obj, "page_qs": page_qs, "deck": deck, "bestseller_ids": bestseller_ids, "cats": Category.objects.all(),
        "q": q, "cat": cat, "sort": sort,
        "craftsmanship": craftsmanship,
        "top_reviews": top_reviews, "liked_ids": liked_ids, "review_stats": review_stats,
    })

def detail(request, pk):
    posters = Poster.objects.select_related("category")
    if not request.user.is_staff:
        posters = posters.filter(is_active=True)   # hidden posters are 404 for customers
    p = get_object_or_404(posters, pk=pk)
    can_review = request.user.is_authenticated and not Review.objects.filter(
        user=request.user, poster=p).exists() and OrderItem.objects.filter(
        poster=p, order__user=request.user).exclude(order__status="Cancelled").exists()
    if request.method == "POST" and can_review:
        form = ReviewForm(request.POST)
        if form.is_valid():
            Review.objects.get_or_create(poster=p, user=request.user, defaults={
                "rating": form.cleaned_data["rating"],
                "text": form.cleaned_data["text"].strip(),
            })
            messages.success(request, "Review posted.")
        else:
            messages.error(request, "Please choose a rating from 1 to 5.")
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
    """Return (items, total) for the session cart, dropping invalid or hidden entries."""
    raw = request.session.get("cart", {})
    parsed = []
    for k, q in raw.items():
        pid, _, size = str(k).partition(":")
        if pid.isdigit() and size in SIZES and isinstance(q, int) and q > 0:
            parsed.append((k, int(pid), size, min(q, MAX_QTY)))
    posters = Poster.objects.filter(is_active=True).select_related("category").in_bulk({p for _, p, _, _ in parsed})
    items, total, clean = [], 0, {}
    for k, pid, size, q in parsed:
        p = posters.get(pid)
        if p:
            pr = p.price(size)
            items.append({"key": k, "poster": p, "size": size, "qty": q, "price": pr, "sub": pr * q})
            total += pr * q
            clean[k] = q
    if clean != raw:
        request.session["cart"] = clean
    return items, total

def cart(request):
    items, total = _cart(request); return render(request, "cart.html", {"items": items, "total": total})

@require_POST
def cart_add(request):
    form = CartAddForm(request.POST)
    if not form.is_valid():
        messages.error(request, "That poster could not be added.")
        return redirect("home")
    p = Poster.objects.filter(pk=form.cleaned_data["poster"], is_active=True).first()
    if not p:
        messages.error(request, "Sorry, that poster is no longer available.")
        return redirect("home")
    c = request.session.get("cart", {}); k = f"{p.pk}:{form.cleaned_data['size']}"
    if c.get(k, 0) >= MAX_QTY:
        messages.info(request, f"You can order up to {MAX_QTY} of the same print.")
    else:
        c[k] = c.get(k, 0) + 1; messages.success(request, "Added to cart.")
    request.session["cart"] = c
    return redirect("cart")

@require_POST
def cart_update(request):
    form = CartUpdateForm(request.POST)
    c = request.session.get("cart", {})
    if form.is_valid() and form.cleaned_data["key"] in c:
        k, a = form.cleaned_data["key"], form.cleaned_data["action"]
        c[k] = min(MAX_QTY, c[k] + {"inc": 1, "dec": -1}.get(a, -c[k]))
        if c[k] < 1: del c[k]
        request.session["cart"] = c
    return redirect("cart")

def _coupon_state(user, code, total):
    """Return (coupon, discount, error). error is '' when the coupon can be used."""
    if not code:
        return None, 0, ""
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        return None, 0, f"Coupon '{code}' not found."
    err = coupon.error_for(user, total)
    if err:
        return None, 0, f"Coupon '{code}' {err}"
    discount = coupon.apply(total)
    if discount == 0:
        return None, 0, f"Coupon '{code}' gives ₹0 discount on your cart."
    return coupon, discount, ""

def _send_confirmation(order, email):
    if not email:
        return
    try:
        send_mail(
            f"PosterHub order #{order.pk} confirmed",
            f"Thanks {order.name}! Your order of ₹{order.total} is being processed.",
            settings.DEFAULT_FROM_EMAIL, [email],
        )
    except Exception:   # a mail problem must never undo or break a placed order
        log.exception("Could not send confirmation for order %s", order.pk)

@login_required
def checkout(request):
    items, total = _cart(request)
    if not items: return redirect("cart")
    action = request.POST.get("action", "") if request.method == "POST" else ""

    if action == "apply_coupon":
        code = request.POST.get("coupon_code", "").strip().upper()
        _, disc, err = _coupon_state(request.user, code, total)
        if err:
            messages.error(request, err)
        else:
            request.session["coupon_code"] = code
            messages.success(request, f"Coupon '{code}' applied — you save ₹{disc}!")
        return redirect("checkout")

    if action == "remove_coupon":
        request.session.pop("coupon_code", None)
        messages.info(request, "Coupon removed.")
        return redirect("checkout")

    coupon, discount, err = _coupon_state(request.user, request.session.get("coupon_code", ""), total)
    if err:   # the saved coupon stopped being valid (expired, used up, first order already placed)
        request.session.pop("coupon_code", None)
        messages.error(request, f"{err} It was removed, so please check your updated total.")
        if action == "place_order":
            return redirect("checkout")   # never charge a different total than the customer saw
    final_total = max(0, total - discount)

    if action == "place_order":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            with transaction.atomic():
                if coupon and Coupon.objects.select_for_update().get(pk=coupon.pk).error_for(request.user, total):
                    request.session.pop("coupon_code", None)
                    messages.error(request, "That coupon is no longer valid, please review your total.")
                    return redirect("checkout")
                o = Order.objects.create(
                    user=request.user, name=cd["name"], address=cd["address"], phone=cd["phone"],
                    payment=cd["payment"], total=final_total,
                    coupon_code=coupon.code if coupon else "", discount_amount=discount,
                )
                OrderItem.objects.bulk_create([
                    OrderItem(order=o, poster=i["poster"], size=i["size"], qty=i["qty"], price=i["price"]) for i in items
                ])
                if coupon:
                    Coupon.objects.filter(pk=coupon.pk).update(times_used=F("times_used") + 1)
            request.session["cart"] = {}
            request.session.pop("coupon_code", None)
            _send_confirmation(o, request.user.email)
            messages.success(request, f"Order #{o.pk} placed successfully!")
            return redirect("orders")
    else:
        prof = Profile.objects.filter(user=request.user).first()
        form = CheckoutForm(initial={
            "name": request.user.get_full_name() or request.user.username,
            "phone": prof.phone if prof else "",
            "address": ", ".join(x for x in (prof.address, prof.city, prof.state, prof.pincode) if x) if prof else "",
            "payment": "Cash on delivery",
        })

    return render(request, "checkout.html", {
        "items": items, "total": total, "coupon": coupon,
        "discount": discount, "final_total": final_total, "form": form,
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
    return render(request, "wishlist.html", {"posters": Poster.objects.filter(wishlist__user=request.user, is_active=True).select_related("category").annotate(avg=APPROVED_AVG)})

@login_required
@require_POST
def wish_toggle(request, pk):
    w = Wishlist.objects.filter(user=request.user, poster_id=pk).first()
    if w:
        w.delete(); messages.info(request, "Removed from wishlist.")
    else:
        poster = get_object_or_404(Poster, pk=pk, is_active=True)
        Wishlist.objects.get_or_create(user=request.user, poster=poster)
        messages.success(request, "Saved to wishlist.")
    nxt = request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect("detail", pk=pk)

def register(request):
    f = RegisterForm(request.POST or None)
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
