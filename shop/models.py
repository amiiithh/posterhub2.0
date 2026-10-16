from django.conf import settings
from django.db import models
from django.utils import timezone

SIZES = {"A4": 1, "A3": 1.6, "A2": 2.4}


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
    rating = models.PositiveSmallIntegerField()
    text = models.TextField()
    is_approved = models.BooleanField(default=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ("user", "poster")
        indexes = [models.Index(fields=["poster", "-created"])]

    def __str__(self):
        return f"Review by {self.user} on {self.poster}"
