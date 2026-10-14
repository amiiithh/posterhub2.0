from django.contrib import admin
from django.db.models import Sum, Count, Avg
from django.utils.html import format_html

from .models import Category, Poster, Wishlist, Order, OrderItem, Review, Profile, Coupon


# ─── Site customisation ──────────────────────────────────────────────────────

admin.site.site_header = "PosterHub Administration"
admin.site.site_title = "PosterHub Admin"
admin.site.index_title = "Store Dashboard"


# ─── Category ────────────────────────────────────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "poster_count")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n=Count("posters"))

    @admin.display(description="# Posters", ordering="_n")
    def poster_count(self, obj):
        return obj._n


# ─── Poster ───────────────────────────────────────────────────────────────────

@admin.register(Poster)
class PosterAdmin(admin.ModelAdmin):
    list_display = ("thumbnail", "title", "artist", "category", "base_price", "is_active", "created")
    list_filter = ("category", "is_active")
    list_editable = ("is_active",)
    search_fields = ("title", "artist", "description")
    readonly_fields = ("created", "updated", "preview")
    list_select_related = ("category",)
    fieldsets = (
        (None, {"fields": ("title", "artist", "category", "description", "is_active")}),
        ("Pricing & Visuals", {"fields": ("base_price", "hue", "image", "preview")}),
        ("Meta", {"fields": ("created", "updated")}),
    )

    @admin.display(description="Image")
    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:40px;border-radius:4px;">',
                obj.image.url,
            )
        return format_html(
            '<div style="width:40px;height:40px;border-radius:4px;'
            'background:hsl({},60%,55%);"></div>',
            obj.hue,
        )

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:200px;border-radius:6px;">',
                obj.image.url,
            )
        return format_html(
            '<div style="width:200px;height:200px;border-radius:6px;'
            'background:hsl({},60%,55%);display:flex;align-items:center;'
            'justify-content:center;color:#fff;font-size:14px;">No image</div>',
            obj.hue,
        )


# ─── Order ────────────────────────────────────────────────────────────────────

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("poster", "size", "qty", "price", "subtotal")
    can_delete = False

    @admin.display(description="Subtotal")
    def subtotal(self, obj):
        return f"₹{obj.qty * obj.price:,}"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "name", "phone", "total_display",
        "payment", "status", "created",
    )
    list_editable = ("status",)
    list_filter = ("status", "payment", "created")
    search_fields = ("user__username", "name", "phone", "address", "coupon_code")
    readonly_fields = ("user", "name", "address", "phone", "payment", "total", "created", "updated")
    list_select_related = ("user",)
    inlines = [OrderItemInline]
    date_hierarchy = "created"

    @admin.display(description="Total (₹)", ordering="total")
    def total_display(self, obj):
        return f"₹{obj.total:,}"

    def changelist_view(self, request, extra_context=None):
        qs = self.get_queryset(request).exclude(status="Cancelled")
        total = qs.aggregate(s=Sum("total"))["s"] or 0
        extra_context = extra_context or {}
        extra_context["title"] = f"Orders — Revenue (excl. cancelled): ₹{total:,}"
        return super().changelist_view(request, extra_context)


# ─── Review ───────────────────────────────────────────────────────────────────

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("poster", "user", "stars", "is_approved", "short_text", "created")
    list_filter = ("rating", "is_approved")
    list_editable = ("is_approved",)
    search_fields = ("user__username", "poster__title", "text")
    readonly_fields = ("poster", "user", "created")
    list_select_related = ("poster", "user")
    ordering = ("-created",)

    @admin.display(description="Rating")
    def stars(self, obj):
        return "★" * obj.rating + "☆" * (5 - obj.rating)

    @admin.display(description="Review")
    def short_text(self, obj):
        return obj.text[:80] + ("…" if len(obj.text) > 80 else "")


# ─── Wishlist ─────────────────────────────────────────────────────────────────

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "poster", "created")
    search_fields = ("user__username", "poster__title")
    list_filter = ("poster__category",)
    list_select_related = ("user", "poster", "poster__category")


# ─── Profile ────────────────────────────────────────────────────────────────

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "city", "state", "pincode", "updated")
    search_fields = ("user__username", "user__email", "phone", "city", "address")
    list_filter = ("state",)
    list_select_related = ("user",)


# ─── Coupon ─────────────────────────────────────────────────────────────────

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "title", "discount", "min_total",
        "max_uses", "times_used", "valid_from", "valid_until", "active", "available_now",
    )
    list_editable = ("active",)
    list_filter = ("kind", "active")
    search_fields = ("code", "title")
    readonly_fields = ("times_used",)
    fieldsets = (
        (None, {"fields": ("code", "title", "active")}),
        ("Discount", {"fields": ("kind", "value", "min_total")}),
        ("Limits", {"fields": ("max_uses", "times_used", "valid_from", "valid_until")}),
    )

    @admin.display(description="Discount")
    def discount(self, obj):
        return obj.display()

    @admin.display(description="Available", boolean=True)
    def available_now(self, obj):
        return obj.is_available()
