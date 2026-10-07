from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from .models import Category, Poster, Wishlist, Order, OrderItem, Review


# ─── Category ────────────────────────────────────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ("name", "slug", "poster_count")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @admin.display(description="# Posters")
    def poster_count(self, obj):
        return obj.posters.count()


# ─── Poster ───────────────────────────────────────────────────────────────────

@admin.register(Poster)
class PosterAdmin(admin.ModelAdmin):
    list_display   = ("thumbnail", "title", "artist", "category", "base_price", "created")
    list_filter    = ("category",)
    search_fields  = ("title", "artist", "description")
    readonly_fields = ("created", "preview")
    fieldsets = (
        (None, {"fields": ("title", "artist", "category", "description")}),
        ("Pricing & Visuals", {"fields": ("base_price", "hue", "image", "preview")}),
        ("Meta", {"fields": ("created",)}),
    )

    @admin.display(description="Image")
    def thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;border-radius:4px;">', obj.image.url)
        return format_html(
            '<div style="width:40px;height:40px;border-radius:4px;'
            'background:hsl({},60%,55%);"></div>', obj.hue
        )

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:200px;border-radius:6px;">', obj.image.url)
        return format_html(
            '<div style="width:200px;height:200px;border-radius:6px;'
            'background:hsl({},60%,55%);display:flex;align-items:center;'
            'justify-content:center;color:#fff;font-size:14px;">No image</div>', obj.hue
        )


# ─── Order ────────────────────────────────────────────────────────────────────

class OrderItemInline(admin.TabularInline):
    model  = OrderItem
    extra  = 0
    readonly_fields = ("poster", "size", "qty", "price")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display   = ("id", "user", "name", "phone", "total_display", "payment", "status", "created")
    list_editable  = ("status",)
    list_filter    = ("status", "payment", "created")
    search_fields  = ("user__username", "name", "phone", "address")
    readonly_fields = ("user", "name", "address", "phone", "payment", "total", "created")
    inlines        = [OrderItemInline]
    date_hierarchy = "created"

    @admin.display(description="Total (₹)", ordering="total")
    def total_display(self, obj):
        return f"₹{obj.total:,}"

    def changelist_view(self, request, extra_context=None):
        qs  = self.get_queryset(request).exclude(status="Cancelled")
        total = qs.aggregate(s=Sum("total"))["s"] or 0
        extra_context = extra_context or {}
        extra_context["title"] = f"Orders — Total Sales: ₹{total:,}"
        return super().changelist_view(request, extra_context)


# ─── Review ───────────────────────────────────────────────────────────────────

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ("poster", "user", "stars", "short_text", "created")
    list_filter   = ("rating",)
    search_fields = ("user__username", "poster__title", "text")
    readonly_fields = ("poster", "user", "created")
    ordering      = ("-created",)

    @admin.display(description="Rating")
    def stars(self, obj):
        return "★" * obj.rating + "☆" * (5 - obj.rating)

    @admin.display(description="Review")
    def short_text(self, obj):
        return obj.text[:80] + ("…" if len(obj.text) > 80 else "")


# ─── Wishlist ─────────────────────────────────────────────────────────────────

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display  = ("user", "poster")
    search_fields = ("user__username", "poster__title")
    list_filter   = ("poster__category",)
