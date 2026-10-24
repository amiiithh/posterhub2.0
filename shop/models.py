from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

SIZES = {"A4": 1, "A3": 1.6, "A2": 2.4}
MAX_CART_QTY = 20   # most copies of one poster and size in a Vault (cart)


class Category(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Poster(models.Model):
    title = models.CharField(max_length=120, db_index=True)
    artist = models.CharField(max_length=80, db_index=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="posters"
    )
    description = models.TextField(blank=True)
    base_price = models.PositiveIntegerField(help_text="A4 price in INR")
    image = models.ImageField(upload_to="posters/", blank=True)
    hue = models.PositiveSmallIntegerField(
        default=210, help_text="0-360, colour of placeholder art"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "-created"]),
            models.Index(fields=["is_active", "-created"]),
        ]

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:   # a new upload: shrink it before it is stored
            from .images import shrink
            small = shrink(self.image.file, self.image.name)
            if small is not None:
                self.image = small
        super().save(*args, **kwargs)

    def price(self, size):
        return round(self.base_price * SIZES[size])

    @property
    def price_a3(self):
        return self.price("A3")

    @property
    def price_a2(self):
        return self.price("A2")

    def __str__(self):
        return self.title


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    poster = models.ForeignKey(Poster, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "poster")
        indexes = [models.Index(fields=["user", "poster"])]


class Order(models.Model):
    STATUS = [(s, s) for s in ("Processing", "Shipped", "Delivered", "Cancelled")]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    payment = models.CharField(max_length=30)
    status = models.CharField(
        max_length=20, choices=STATUS, default="Processing", db_index=True
    )
    total = models.PositiveIntegerField()
    coupon_code = models.CharField(max_length=20, blank=True)
    discount_amount = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, help_text="Internal staff notes")
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-created"]),
            models.Index(fields=["user", "-created"]),
        ]

    def __str__(self):
        return f"Order #{self.pk}"

    TRANSITIONS = {
        "Processing": {"Shipped", "Cancelled"},
        "Shipped": {"Delivered", "Cancelled"},
        "Delivered": set(),
        "Cancelled": set(),
    }

    @transaction.atomic
    def change_status(self, new):
        """Move the order to a new status. Returns (changed, message). Cancelling gives the coupon use back."""
        locked = Order.objects.select_for_update().get(pk=self.pk)
        if new == locked.status:
            return False, f"Order #{self.pk} is already {new}."
        if new not in self.TRANSITIONS.get(locked.status, set()):
            return False, f"Order #{self.pk} can't go from {locked.status} to {new}."
        self.status = new
        self.save(update_fields=["status", "updated"])
        if new == "Cancelled" and self.coupon_code:
            Coupon.objects.filter(code=self.coupon_code, times_used__gt=0).update(
                times_used=models.F("times_used") - 1
            )
        return True, f"Order #{self.pk} status is now {new}."

    def recalculate(self):
        """Recompute discount and total from the current item quantities (does not save)."""
        subtotal = sum(i.qty * i.price for i in self.items.all())
        discount = self.discount_amount
        if self.coupon_code:
            coupon = Coupon.objects.filter(code=self.coupon_code).first()
            if coupon and coupon.kind == "percent":
                discount = round(subtotal * coupon.value / 100)
            elif coupon:
                discount = min(coupon.value, subtotal)
            else:
                discount = min(discount, subtotal)
        self.discount_amount = discount
        self.total = max(0, subtotal - discount)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    poster = models.ForeignKey(
        Poster, on_delete=models.SET_NULL, null=True, related_name="order_items"
    )
    size = models.CharField(max_length=3)
    qty = models.PositiveIntegerField()
    price = models.PositiveIntegerField()

    class Meta:
        indexes = [models.Index(fields=["order", "poster"])]


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=60, blank=True)
    state = models.CharField(max_length=60, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


class Coupon(models.Model):
    KIND = [("percent", "Percent off"), ("flat", "Flat INR off")]
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=KIND, default="percent")
    value = models.PositiveIntegerField(help_text="Percent (1-100) or flat INR amount")
    min_total = models.PositiveIntegerField(
        default=0, help_text="Minimum cart total in INR"
    )
    max_uses = models.PositiveIntegerField(
        null=True, blank=True, help_text="Max redemptions (blank = unlimited)"
    )
    times_used = models.PositiveIntegerField(default=0)
    valid_from = models.DateField(null=True, blank=True, help_text="Blank = always valid")
    valid_until = models.DateField(
        null=True, blank=True, help_text="Blank = never expires"
    )
    active = models.BooleanField(default=True, db_index=True)
    first_order_only = models.BooleanField(
        default=False, help_text="Only valid on a customer's first (non-cancelled) order"
    )

    class Meta:
        indexes = [models.Index(fields=["active", "valid_until"])]

    def is_available(self):
        today = timezone.localdate()
        if not self.active:
            return False
        if self.valid_from and self.valid_from > today:
            return False
        if self.valid_until and self.valid_until < today:
            return False
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False
        return True

    def error_for(self, user, total):
        """Why this coupon can't be used right now ('' when it can)."""
        if not self.is_available():
            return "is expired or unavailable."
        if total < self.min_total:
            return f"needs a minimum order of ₹{self.min_total}."
        if self.first_order_only and Order.objects.filter(user=user).exclude(status="Cancelled").exists():
            return "is valid on your first order only."
        return ""

    def apply(self, total):
        """Return the discount amount for a given cart total."""
        if not self.is_available() or total < self.min_total:
            return 0
        if self.kind == "percent":
            return round(total * self.value / 100)
        return min(self.value, total)

    def display(self):
        return f"{self.value}% OFF" if self.kind == "percent" else f"₹{self.value} OFF"

    def __str__(self):
        return self.code


class Review(models.Model):
    poster = models.ForeignKey(
        Poster, on_delete=models.CASCADE, related_name="reviews"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    text = models.TextField()
    is_approved = models.BooleanField(default=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked_reviews", blank=True
    )

    @property
    def stars(self):
        return [i <= self.rating for i in range(1, 6)]

    class Meta:
        unique_together = ("user", "poster")
        indexes = [models.Index(fields=["poster", "-created"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_between_1_and_5",
            )
        ]

    def __str__(self):
        return f"Review by {self.user} on {self.poster}"


class CartItem(models.Model):
    """One line of a signed-in customer's saved Vault (cart)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items")
    poster = models.ForeignKey(Poster, on_delete=models.CASCADE, related_name="cart_items")
    size = models.CharField(max_length=3)
    qty = models.PositiveSmallIntegerField(default=1)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "poster", "size"], name="one_cart_line_per_user_poster_size"),
            models.CheckConstraint(condition=models.Q(qty__gte=1, qty__lte=MAX_CART_QTY), name="cart_qty_between_1_and_20"),
        ]

    def __str__(self):
        return f"{self.user} - {self.poster} {self.size} x{self.qty}"

