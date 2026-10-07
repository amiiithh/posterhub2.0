from django.conf import settings
from django.db import models

SIZES = {"A4": 1, "A3": 1.6, "A2": 2.4}

class Category(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(unique=True)
    class Meta: verbose_name_plural = "categories"
    def __str__(self): return self.name

class Poster(models.Model):
    title = models.CharField(max_length=120)
    artist = models.CharField(max_length=80)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="posters")
    description = models.TextField(blank=True)
    base_price = models.PositiveIntegerField(help_text="A4 price in INR")
    image = models.ImageField(upload_to="posters/", blank=True)
    hue = models.PositiveSmallIntegerField(default=210, help_text="0-360, colour of placeholder art")
    created = models.DateTimeField(auto_now_add=True)
    def price(self, size): return round(self.base_price * SIZES[size])
    def __str__(self): return self.title

class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    poster = models.ForeignKey(Poster, on_delete=models.CASCADE)
    class Meta: unique_together = ("user", "poster")

class Order(models.Model):
    STATUS = [(s, s) for s in ("Processing", "Shipped", "Delivered", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    payment = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=STATUS, default="Processing")
    total = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Order #{self.pk}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    poster = models.ForeignKey(Poster, on_delete=models.SET_NULL, null=True)
    size = models.CharField(max_length=3)
    qty = models.PositiveIntegerField()
    price = models.PositiveIntegerField()

class Review(models.Model):
    poster = models.ForeignKey(Poster, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ("user", "poster")
