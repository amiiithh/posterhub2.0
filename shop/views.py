from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.mail import send_mail
from django.db.models import Avg, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .models import *

def home(request):
    q, cat, sort = request.GET.get("q", ""), request.GET.get("cat", ""), request.GET.get("sort", "")
    ps = Poster.objects.annotate(avg=Avg("reviews__rating"))
    if q: ps = ps.filter(Q(title__icontains=q) | Q(artist__icontains=q) | Q(description__icontains=q))
    if cat: ps = ps.filter(category__slug=cat)
    ps = ps.order_by({"lo": "base_price", "hi": "-base_price"}.get(sort, "-created"))
    craftsmanship = [
        ("fa-solid fa-scroll", "300 GSM Archival Velvet", "Heavy museum-grade Fuji matte pulp. Zero glare, zero reflection under spotlighting."),
        ("fa-solid fa-droplet", "12-Color Giclée Glaze", "Lucia Pro archival pigment inks yielding 100+ year colour fidelity and deep obsidian blacks."),
        ("fa-solid fa-hand-holding-hand", "Zero-Damage Nano Tabs", "Industrial micro-suction strips peel cleanly off delicate Indian wall putty without peeling paint."),
        ("fa-solid fa-box-archive", "Reinforced Tube Pack", "Double-wall rigid spiral cylinders with moisture barrier parchment for weather immunity."),
    ]
    testimonials = [
        ("Aditya S.", "Architect, Indiranagar, Bengaluru", "The velvet matte texture is phenomenal. There is zero glare under my high-CRI studio lights. The nano tabs peel cleanly without tearing paint off rented apartment walls."),
        ("Kabir Mehra", "Creative Lead, Bandra West, Mumbai", "Got the 6-piece Porsche GT set. The 300 GSM paper has serious physical weight. It feels like museum collection prints rather than typical commercial glossy posters."),
        ("Rhea Sen", "Interior Stylist, Vasant Kunj, New Delhi", "Dispatch was rapid and arrived in a super-rigid heavy tube. No bent corners or creases. The 'Buy 4 Get 3 Free' bundle deal gave me enough prints to furnish two entire rooms."),
    ]
    return render(request, "home.html", {
        "posters": ps, "cats": Category.objects.all(),
        "q": q, "cat": cat, "sort": sort,
        "craftsmanship": craftsmanship,
        "testimonials": testimonials,
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
    return render(request, "detail.html", {
        "p": p,
        "sizes": [(s, p.price(s)) for s in SIZES],
        "can_review": can_review,
        "wished": wished,
        "reviews": p.reviews.select_related("user").order_by("-created"),
        "avg": p.reviews.aggregate(a=Avg("rating"))["a"],
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
    if request.method == "POST":
        o = Order.objects.create(user=request.user, name=request.POST["name"], address=request.POST["address"],
            phone=request.POST["phone"], payment=request.POST["payment"], total=total)
        for i in items: OrderItem.objects.create(order=o, poster=i["poster"], size=i["size"], qty=i["qty"], price=i["price"])
        request.session["cart"] = {}
        send_mail(
            f"PosterHub order #{o.pk} confirmed",
            f"Thanks {o.name}! Your order of ₹{total} is being processed.",
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email or "noreply@posterhub.com"],
        )
        messages.success(request, f"Order #{o.pk} placed successfully!")
        return redirect("orders")
    return render(request, "checkout.html", {"items": items, "total": total})

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
    if not made: w.delete()
    return redirect("detail", pk=pk)

def register(request):
    f = UserCreationForm(request.POST or None)
    if request.method == "POST" and f.is_valid():
        login(request, f.save()); return redirect("home")
    return render(request, "registration/register.html", {"form": f})

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

