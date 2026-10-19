from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.text import slugify

from .models import SIZES, Poster, Category, Order, OrderItem, Coupon


class AddEditPosterForm(forms.ModelForm):
    class Meta:
        model = Poster
        fields = [
            "title", "artist", "category", "description",
            "base_price", "image", "hue", "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "base_price": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "hue": forms.NumberInput(attrs={"min": "0", "max": "360", "step": "1"}),
        }

    def clean_base_price(self):
        v = self.cleaned_data["base_price"]
        if v is None or v < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return v


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug"]
        widgets = {
            "slug": forms.TextInput(attrs={"placeholder": "auto-generated from name"}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        if not slug:
            slug = slugify(self.cleaned_data.get("name", ""))
        return slug


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code", "title", "kind", "value",
            "min_total", "max_uses", "valid_from", "valid_until", "active", "first_order_only",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"style": "text-transform:uppercase"}),
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean_value(self):
        val = self.cleaned_data["value"]
        kind = self.cleaned_data.get("kind", "percent")
        if kind == "percent" and not (1 <= val <= 100):
            raise forms.ValidationError("Percent discount must be between 1 and 100.")
        if val <= 0:
            raise forms.ValidationError("Discount value must be positive.")
        return val


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["name", "phone", "address", "payment", "status", "notes"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_phone(self):
        v = self.cleaned_data["phone"].replace(" ", "").replace("-", "")
        if not v.lstrip("+").isdigit() or len(v.lstrip("+")) < 8:
            raise forms.ValidationError("Enter a valid phone number.")
        return v


def clean_phone_number(value):
    v = value.replace(" ", "").replace("-", "")
    digits = v[1:] if v.startswith("+") else v
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise forms.ValidationError("Enter a valid phone number (8 to 15 digits).")
    return v


class CheckoutForm(forms.Form):
    PAYMENTS = [("Cash on delivery", "Cash on delivery"), ("Online (simulated)", "Online (simulated)")]
    name = forms.CharField(max_length=100)
    phone = forms.CharField(max_length=20)
    address = forms.CharField(max_length=500, widget=forms.Textarea)
    payment = forms.ChoiceField(choices=PAYMENTS)

    def clean_phone(self):
        return clean_phone_number(self.cleaned_data["phone"])

    def clean_address(self):
        v = self.cleaned_data["address"].strip()
        if len(v) < 8:
            raise forms.ValidationError("Please enter your full shipping address.")
        return v


class CartAddForm(forms.Form):
    poster = forms.IntegerField(min_value=1)
    size = forms.ChoiceField(choices=[(k, k) for k in SIZES], required=False)

    def clean_size(self):
        return self.cleaned_data.get("size") or "A4"


class CartUpdateForm(forms.Form):
    key = forms.CharField(max_length=40)
    action = forms.ChoiceField(choices=[("inc", "inc"), ("dec", "dec"), ("del", "del")])


class ReviewForm(forms.Form):
    rating = forms.IntegerField(min_value=1, max_value=5)
    text = forms.CharField(max_length=1000, required=False)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Used for your order confirmations.")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
