"""
PosterHub – Custom admin views.

All views enforce staff/superuser access via _staff_required().
URLs are prefixed with /manage/ to avoid clashing with Django's built-in /admin/.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ExpressionWrapper, F, IntegerField, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AddEditPosterForm, CouponForm, CategoryForm
from .models import Poster, Category, Order, OrderItem, Review, Coupon, Wishlist

User = get_user_model()

PAGE_SIZE = 25


# ── Access control ────────────────────────────────────────────────────────────

def _staff_required(view_fn):
    """Decorator: login + staff/superuser guard."""
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "Staff access required.")
            return redirect("home")
        return view_fn(request, *args, **kwargs)
    _wrapped.__name__ = view_fn.__name__
    return _wrapped


# ── Dashboard ─────────────────────────────────────────────────────────────────

@_staff_required
def admin_dashboard(request):
    """Analytics overview: revenue, funnel, top sellers, recent activity."""
    total_revenue = Order.objects.aggregate(s=Sum("total"))["s"] or 0
    orders_placed = Order.objects.count()
    delivered_revenue = (
        Order.objects.filter(status="Delivered").aggregate(s=Sum("total"))["s"] or 0
    )
    processing = Order.objects.filter(status="Processing").count()
    shipped = Order.objects.filter(status="Shipped").count()
    delivered = Order.objects.filter(status="Delivered").count()
    cancelled = Order.objects.filter(status="Cancelled").count()
    n_items = OrderItem.objects.aggregate(s=Sum("qty"))["s"] or 0

    # Top sellers by units sold
    top_sellers = (
        Poster.objects.annotate(t=Sum("order_items__qty"))
        .filter(t__gt=0)
        .order_by("-t")[:8]
    )

    recent_orders = Order.objects.select_related("user").order_by("-created")[:5]

    # Active + non-expired coupons (Python-filtered because of date check)
    active_coupons = sum(1 for c in Coupon.objects.filter(active=True) if c.is_available())

    reviews_total = Review.objects.count()
    avg_rating_raw = Review.objects.aggregate(a=Avg("rating"))["a"] or 0
    avg_stars = round(avg_rating_raw, 1) if reviews_total else 0

    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    total_posters = Poster.objects.filter(is_active=True).count()

    status_colors = {
        "Processing": "#f59e0b",
        "Shipped": "#3b82f6",
        "Delivered": "#34d399",
        "Cancelled": "#ef4444",
    }
    status_data = [
        {
            "label": s,
            "count": Order.objects.filter(status=s).count(),
            "color": status_colors[s],
        }
        for s in ("Processing", "Shipped", "Delivered", "Cancelled")
    ]

    # Revenue split by payment method
    payment_breakdown = (
        Order.objects.exclude(status="Cancelled")
        .values("payment")
        .annotate(total=Sum("total"), count=Count("id"))
        .order_by("-total")[:6]
    )

    # Top categories by order volume
    top_categories = (
        Category.objects.annotate(
            units=Sum("posters__order_items__qty")
        )
        .filter(units__gt=0)
        .order_by("-units")[:6]
    )

    context = {
        "total_revenue": total_revenue,
        "orders_placed": orders_placed,
        "delivered_revenue": delivered_revenue,
        "processing": processing,
        "shipped": shipped,
        "delivered": delivered,
        "cancelled": cancelled,
        "items_shipped": n_items,
        "top_sellers": top_sellers,
        "recent_orders": recent_orders,
        "coupons": active_coupons,
        "reviews": reviews_total,
        "avg_stars": avg_stars,
        "status_data": status_data,
        "total_users": total_users,
        "active_users": active_users,
        "total_posters": total_posters,
        "payment_breakdown": payment_breakdown,
        "top_categories": top_categories,
    }
    return render(request, "admin_dashboard.html", context)


# ── Orders ────────────────────────────────────────────────────────────────────

@_staff_required
def admin_orders(request):
    """List orders with search, status filter, pagination, and inline status update."""
    qs = Order.objects.select_related("user").prefetch_related("items").order_by("-created")

    # Status filter
    status_filter = request.GET.get("status", "")
    if status_filter in dict(Order.STATUS):
        qs = qs.filter(status=status_filter)

    # Search: order id, username, name, phone
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(id__icontains=q) |
            Q(user__username__icontains=q) |
            Q(name__icontains=q) |
            Q(phone__icontains=q)
        )

    # Inline status update
    if request.method == "POST" and "status" in request.POST:
        pk = request.POST.get("order_id")
        st = request.POST.get("status")
        o = get_object_or_404(Order, pk=pk)
        if st in dict(Order.STATUS):
            changed, msg = o.change_status(st)
            (messages.success if changed else messages.error)(request, msg)
        return redirect(request.get_full_path())

    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    total_sales = Order.objects.exclude(status="Cancelled").aggregate(s=Sum("total"))["s"] or 0

    context = {
        "orders": page,
        "page_obj": page,
        "total_sales": total_sales,
        "orders_count": Order.objects.count(),
        "processing_count": Order.objects.filter(status="Processing").count(),
        "shipped_count": Order.objects.filter(status="Shipped").count(),
        "statuses": Order.STATUS,
        "status_filter": status_filter,
        "q": q,
    }
    return render(request, "admin_orders.html", context)


@_staff_required
def admin_order_detail(request, pk):
    """Single order: edit item qtys, update status, add staff notes, cancel."""
    o = get_object_or_404(Order, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_qty":
            if o.status != "Processing":
                messages.error(request, f"Quantities can only be changed while an order is Processing (this one is {o.status}).")
                return redirect("admin_order_detail", pk=pk)
            for i in o.items.all():
                key = f"qty-{i.pk}"
                if key in request.POST:
                    try:
                        i.qty = min(99, max(1, int(request.POST[key])))
                        i.save(update_fields=["qty"])
                    except ValueError:
                        pass
            o.recalculate()
            o.save(update_fields=["total", "discount_amount", "updated"])
            messages.success(request, f"Item quantities updated. New order total: ₹{o.total}.")
            return redirect("admin_order_detail", pk=pk)

        elif action == "update_status":
            st = request.POST.get("status")
            if st in dict(Order.STATUS):
                changed, msg = o.change_status(st)
                (messages.success if changed else messages.error)(request, msg)
            return redirect("admin_order_detail", pk=pk)

        elif action == "save_notes":
            o.notes = request.POST.get("notes", "")
            o.save(update_fields=["notes", "updated"])
            messages.success(request, "Notes saved.")
            return redirect("admin_order_detail", pk=pk)

        elif action == "cancel":
            changed, msg = o.change_status("Cancelled")
            (messages.warning if changed else messages.error)(request, f"Order #{pk} cancelled." if changed else msg)
            return redirect("admin_orders")

    items = o.items.select_related("poster__category").order_by("size")   # OrderItem.subtotal is a property

    return render(
        request,
        "admin_order_detail.html",
        {"order": o, "items": items, "statuses": Order.STATUS},
    )


# ── Posters ───────────────────────────────────────────────────────────────────

@_staff_required
def admin_posters(request):
    """List all posters with search/filter, and handle Add-new form."""
    if request.method == "POST":
        form = AddEditPosterForm(request.POST, request.FILES)
        if form.is_valid():
            poster = form.save()
            messages.success(request, f"Poster '{poster.title}' added.")
            return redirect("admin_posters")
    else:
        form = AddEditPosterForm()

    qs = Poster.objects.select_related("category").order_by("-created")

    # Search
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(artist__icontains=q))

    # Category filter
    cat_filter = request.GET.get("cat", "")
    if cat_filter:
        qs = qs.filter(category__slug=cat_filter)

    # Active filter
    active_filter = request.GET.get("active", "")
    if active_filter == "1":
        qs = qs.filter(is_active=True)
    elif active_filter == "0":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    cats = Category.objects.annotate(n=Count("posters")).order_by("-n")[:16]

    return render(
        request,
        "admin_posters.html",
        {
            "form": form,
            "posters": page,
            "page_obj": page,
            "cats": cats,
            "q": q,
            "cat_filter": cat_filter,
            "active_filter": active_filter,
            "all_cats": Category.objects.order_by("name"),
        },
    )


@_staff_required
def admin_poster_edit(request, pk):
    """Edit a poster."""
    p = get_object_or_404(Poster, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "toggle_active":
            p.is_active = not p.is_active
            p.save(update_fields=["is_active", "updated"])
            state = "activated" if p.is_active else "deactivated"
            messages.success(request, f"Poster '{p.title}' {state}.")
            return redirect("admin_poster_edit", pk=pk)
        form = AddEditPosterForm(request.POST, request.FILES, instance=p)
        if form.is_valid():
            form.save()
            messages.success(request, f"Poster '{p.title}' updated.")
            return redirect("admin_posters")
    else:
        form = AddEditPosterForm(instance=p)
    return render(request, "admin_poster_edit.html", {"form": form, "poster": p})


@_staff_required
@require_POST
def admin_poster_delete(request, pk):
    """Soft-delete: deactivate a poster instead of hard-deleting."""
    p = get_object_or_404(Poster, pk=pk)
    p.is_active = False
    p.save(update_fields=["is_active", "updated"])
    messages.warning(request, f"Poster '{p.title}' deactivated.")
    return redirect("admin_posters")


# ── Categories ────────────────────────────────────────────────────────────────

@_staff_required
def admin_categories(request):
    """CRUD for categories."""
    if request.method == "POST":
        action = request.POST.get("action", "add")
        if action == "delete":
            cat = get_object_or_404(Category, pk=request.POST.get("cat_id"))
            if cat.posters.exists():
                messages.error(request, f"Cannot delete '{cat.name}' — it still has posters.")
            else:
                name = cat.name
                cat.delete()
                messages.success(request, f"Category '{name}' deleted.")
            return redirect("admin_categories")
        form = CategoryForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Category '{cat.name}' created.")
            return redirect("admin_categories")
    else:
        form = CategoryForm()

    cats = Category.objects.annotate(n=Count("posters")).order_by("name")
    return render(request, "admin_categories.html", {"form": form, "cats": cats})


@_staff_required
def admin_category_edit(request, pk):
    """Edit an existing category."""
    cat = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{cat.name}' updated.")
            return redirect("admin_categories")
    else:
        form = CategoryForm(instance=cat)
    return render(request, "admin_category_edit.html", {"form": form, "cat": cat})


# ── Coupons ───────────────────────────────────────────────────────────────────

@_staff_required
def admin_coupons(request):
    """List & create coupons."""
    if request.method == "POST":
        form = CouponForm(request.POST)
        if form.is_valid():
            coupon = form.save()
            messages.success(request, f"Coupon '{coupon.code}' created.")
            return redirect("admin_coupons")
    else:
        form = CouponForm()

    qs = Coupon.objects.order_by("-active", "-id")
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "admin_coupons.html",
        {"form": form, "coupons": page, "page_obj": page},
    )


@_staff_required
def admin_coupon_edit(request, pk):
    """Edit an existing coupon."""
    coupon = get_object_or_404(Coupon, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "delete":
            code = coupon.code
            coupon.delete()
            messages.warning(request, f"Coupon '{code}' deleted.")
            return redirect("admin_coupons")
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            messages.success(request, f"Coupon '{coupon.code}' updated.")
            return redirect("admin_coupons")
    else:
        form = CouponForm(instance=coupon)
    return render(request, "admin_coupon_edit.html", {"form": form, "coupon": coupon})


# ── Users ─────────────────────────────────────────────────────────────────────

@_staff_required
def admin_users(request):
    """List users with search and inline staff-toggle (superusers only)."""
    if not request.user.is_superuser:
        messages.error(request, "Superuser access required.")
        return redirect("admin_dashboard")

    qs = User.objects.annotate(
        order_count=Count("orders"),
        total_spent=Sum("orders__total", filter=~Q(orders__status="Cancelled")),
    ).order_by("-date_joined")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q)
        )

    # Toggle staff flag
    if request.method == "POST" and request.user.is_superuser:
        uid = request.POST.get("user_id")
        toggle = request.POST.get("toggle")
        u = get_object_or_404(User, pk=uid)
        if u.pk == request.user.pk:
            messages.error(request, "You can't change your own account here, so you can't lock yourself out.")
        elif u.is_superuser and toggle == "staff":
            messages.error(request, "A superuser's staff flag can't be changed here.")
        elif toggle == "staff":
            u.is_staff = not u.is_staff
            u.save(update_fields=["is_staff"])
            messages.success(request, f"Staff flag toggled for {u.username}.")
        elif toggle == "active":
            u.is_active = not u.is_active
            u.save(update_fields=["is_active"])
            messages.success(request, f"Active flag toggled for {u.username}.")
        return redirect(request.get_full_path())

    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "admin_users.html", {"users": page, "page_obj": page, "q": q})


# ── Reviews ───────────────────────────────────────────────────────────────────

@_staff_required
def admin_reviews(request):
    """List reviews; approve/reject inline."""
    qs = Review.objects.select_related("user", "poster").order_by("-created")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(poster__title__icontains=q))

    if request.method == "POST":
        rid = request.POST.get("review_id")
        action = request.POST.get("action")
        rev = get_object_or_404(Review, pk=rid)
        if action == "approve":
            rev.is_approved = True
            rev.save(update_fields=["is_approved"])
            messages.success(request, "Review approved.")
        elif action == "reject":
            rev.is_approved = False
            rev.save(update_fields=["is_approved"])
            messages.warning(request, "Review hidden.")
        elif action == "delete":
            rev.delete()
            messages.warning(request, "Review deleted.")
        return redirect(request.get_full_path())

    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "admin_reviews.html", {"reviews": page, "page_obj": page, "q": q})
