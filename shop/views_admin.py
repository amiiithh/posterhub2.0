from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AddEditPosterForm
from .models import Poster, Category, Order, OrderItem, Review, Coupon


@login_required
def admin_posters(request):
    """Add / edit posters (restricted to staff)."""
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("home")
    if request.method == "POST":
        form = AddEditPosterForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            form.save()
            return redirect("admin_posters")
    else:
        form = AddEditPosterForm()
    qs = Poster.objects.order_by("-created")
    # Count posters per category (Sum would add up poster IDs instead of counting).
    cats = Category.objects.annotate(n=Count("posters")).order_by("-n")[:12]
    return render(request, "admin_posters.html", {"form": form, "categories": qs, "cats": cats})


@login_required
def admin_poster_edit(request, pk):
    """Edit a poster (restricted to staff)."""
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("home")
    p = get_object_or_404(Poster, pk=pk)
    if request.method == "POST":
        form = AddEditPosterForm(request.POST or None, request.FILES or None, instance=p)
        if form.is_valid():
            form.save()
            return redirect("admin_posters")
    else:
        form = AddEditPosterForm(instance=p)
    return render(request, "admin_poster_edit.html", {"form": form, "poster": p})


@login_required
def admin_orders(request):
    """List every order with inline management (restricted to staff)."""
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("home")
    qs = Order.objects.select_related("user").prefetch_related("items__poster").order_by("-created")
    if request.method == "POST" and "status" in request.POST:
        pk, st = request.POST["order_id"], request.POST["status"]
        o = get_object_or_404(Order, pk=pk)
        if st in dict(Order.STATUS):
            o.status = st
            o.save()
        return redirect("admin_orders")
    return render(request, "admin_orders.html", {"orders": qs})


@login_required
def admin_order_detail(request, pk):
    """Single order with editable item qty (restricted to staff)."""
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("home")
    o = get_object_or_404(Order, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            for i in o.items.all():
                if "qty-%d" % i.pk in request.POST:
                    try:
                        q = int(request.POST.get("qty-%d" % i.pk))
                        if q < 1:
                            q = 1
                        i.qty = q
                        i.save()
                    except ValueError:
                        pass
            return redirect("admin_order_detail", pk=pk)
        elif action == "cancel":
            if o.status == "Processing":
                o.status = "Cancelled"
                o.save()
            return redirect("admin_orders")
    items = o.items.select_related("poster").order_by("size")
    return render(request, "admin_order_detail.html", {"order": o, "items": items, "statuses": Order.STATUS})


@login_required
def admin_dashboard(request):
    """Admin analytics page: revenue, orders, stock, top sellers."""
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("home")
    total = Order.objects.aggregate(s=Sum("total"))["s"] or 0
    orders = Order.objects.count()  # number of orders (was wrongly a revenue sum)
    delivered = Order.objects.filter(status="Delivered").aggregate(s=Sum("total"))["s"] or 0
    processing = Order.objects.filter(status="Processing").count()
    shipped = Order.objects.filter(status="Shipped").count()
    cancelled = Order.objects.filter(status="Cancelled").count()
    n_items = OrderItem.objects.aggregate(s=Sum("qty"))["s"] or 0
    # Dashboard context
    total = Order.objects.aggregate(s=Sum("total"))["s"] or 0
    # Admin orders context
    total_sales = Order.objects.aggregate(s=Sum("total"))["s"] or 0
    processing_count = Order.objects.filter(status="Processing").count()
    shipped_count = Order.objects.filter(status="Shipped").count()
    # Poster -> OrderItem reverse name is "orderitem" (OrderItem.poster has no related_name).
    top = (
        Poster.objects.annotate(t=Sum("orderitem__qty"))
        .filter(t__gt=0)
        .order_by("-t")[:8]
    )
    recents = Order.objects.select_related("user").order_by("-created")[:5]
    # is_available() checks the active flag AND the expiry date, so count in Python.
    coupons = sum(1 for c in Coupon.objects.filter(active=True) if c.is_available())
    reviews = Review.objects.count()
    avg_stars = Review.objects.aggregate(a=Sum("rating"), n=Sum("rating"))["a"] or 0
    star_avg = (round(avg_stars / max(1, reviews), 1) if reviews else 0)
    # Per-status order counts + color for the dashboard status bars.
    status_counts = {s: Order.objects.filter(status=s).count() for s in ("Processing", "Shipped", "Delivered", "Cancelled")}
    status_colors = {
        "Processing": "#f59e0b",
        "Shipped": "#3b82f6",
        "Delivered": "#34d399",
        "Cancelled": "#ef4444",
    }
    context = {
        "total_revenue": total,
        "orders_placed": orders,
        "delivered_revenue": delivered,
        "processing": processing,
        "shipped": shipped,
        "cancelled": cancelled,
        "items_shipped": n_items,
        "top_sellers": top,
        "recent_orders": recents,
        "coupons": coupons,
        "reviews": reviews,
        "avg_stars": star_avg,
    }
    return render(request, "admin_dashboard.html", context)
