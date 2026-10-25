import os
import shutil
import subprocess
import sys
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.conf import settings
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from PIL import Image

from . import images
from .models import CartItem, Category, Coupon, Order, OrderItem, Poster, Review, Wishlist

PW = "pw-Test-12345"
GOOD_CHECKOUT = {
    "action": "place_order", "name": "Test User", "phone": "+91 98765 43210",
    "address": "12 MG Road, Kochi, Kerala 682016", "payment": "Cash on delivery",
}


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name="Movies", slug="movies")
        cls.p1 = Poster.objects.create(title="Alpha", artist="A", category=cls.cat, base_price=400)
        cls.p2 = Poster.objects.create(title="Beta", artist="B", category=cls.cat, base_price=500)
        cls.hidden = Poster.objects.create(title="Hidden", artist="H", category=cls.cat, base_price=300, is_active=False)
        cls.user = User.objects.create_user("buyer", "buyer@example.com", PW)
        cls.other = User.objects.create_user("other", "other@example.com", PW)
        cls.staff = User.objects.create_user("staffer", "s@example.com", PW, is_staff=True)

    def setUp(self):
        cache.clear()

    current_user = None

    def login(self, user=None):
        self.current_user = user or self.user
        self.client.force_login(self.current_user)

    def put_in_cart(self, poster=None, size="A4", qty=1):
        """Replace the Vault: saved on the account when signed in, otherwise in the browser session."""
        poster = poster or self.p1
        if self.current_user:
            CartItem.objects.filter(user=self.current_user).delete()
            CartItem.objects.create(user=self.current_user, poster=poster, size=size, qty=qty)
        else:
            s = self.client.session
            s["cart"] = {f"{poster.pk}:{size}": qty}
            s.save()

    def cart_lines(self):
        if self.current_user:
            return {f"{i.poster_id}:{i.size}": i.qty for i in CartItem.objects.filter(user=self.current_user)}
        return dict(self.client.session.get("cart", {}))

    def make_order(self, user=None, poster=None, status="Processing", qty=1):
        o = Order.objects.create(user=user or self.user, name="n", address="a", phone="12345678",
                                 payment="Cash on delivery", total=1, status=status)
        OrderItem.objects.create(order=o, poster=poster or self.p1, size="A4", qty=qty, price=1)
        return o


class CartTests(Base):
    def test_add_valid_poster(self):
        r = self.client.post(reverse("cart_add"), {"poster": self.p1.pk, "size": "A3"})
        self.assertRedirects(r, reverse("cart"))
        self.assertEqual(self.client.session["cart"], {f"{self.p1.pk}:A3": 1})

    def test_add_bad_input_never_crashes(self):
        for data in ({"poster": "abc"}, {}, {"poster": "-4"}, {"poster": 99999}, {"poster": self.p1.pk, "size": "A9"}):
            r = self.client.post(reverse("cart_add"), data)
            self.assertEqual(r.status_code, 302, data)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_inactive_poster_cannot_be_added(self):
        self.client.post(reverse("cart_add"), {"poster": self.hidden.pk})
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_update_bad_input_never_crashes(self):
        self.put_in_cart()
        for data in ({}, {"key": "nope", "action": "inc"}, {"key": f"{self.p1.pk}:A4", "action": "explode"}):
            self.assertEqual(self.client.post(reverse("cart_update"), data).status_code, 302)

    def test_update_inc_dec_delete(self):
        self.put_in_cart(qty=2)
        key = f"{self.p1.pk}:A4"
        self.client.post(reverse("cart_update"), {"key": key, "action": "inc"})
        self.assertEqual(self.client.session["cart"][key], 3)
        self.client.post(reverse("cart_update"), {"key": key, "action": "dec"})
        self.assertEqual(self.client.session["cart"][key], 2)
        self.client.post(reverse("cart_update"), {"key": key, "action": "del"})
        self.assertEqual(self.client.session["cart"], {})

    def test_quantity_is_capped(self):
        self.put_in_cart(qty=20)
        self.client.post(reverse("cart_add"), {"poster": self.p1.pk})
        self.assertEqual(self.client.session["cart"][f"{self.p1.pk}:A4"], 20)

    def test_vault_number_matches_what_the_cart_shows(self):
        s = self.client.session
        s["cart"] = {"garbage": 4, f"{self.p1.pk}:A9": 2, f"{self.hidden.pk}:A4": 3, f"{self.p1.pk}:A4": 2, f"{self.p2.pk}:A3": 1}
        s.save()
        self.assertEqual(self.client.get(reverse("home")).context["cart_count"], 3)
        self.assertEqual(sum(i["qty"] for i in self.client.get(reverse("cart")).context["items"]), 3)

    def test_vault_number_follows_adds_and_removals(self):
        self.client.post(reverse("cart_add"), {"poster": self.p1.pk})
        self.client.post(reverse("cart_add"), {"poster": self.p1.pk})
        self.assertEqual(self.client.get(reverse("home")).context["cart_count"], 2)
        self.client.post(reverse("cart_update"), {"key": f"{self.p1.pk}:A4", "action": "del"})
        self.assertEqual(self.client.get(reverse("home")).context["cart_count"], 0)

    def test_corrupt_or_hidden_entries_are_dropped(self):
        s = self.client.session
        s["cart"] = {"garbage": 1, f"{self.p1.pk}:A9": 1, f"{self.hidden.pk}:A4": 1, f"{self.p2.pk}:A4": 2}
        s.save()
        r = self.client.get(reverse("cart"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total"], 1000)


class CheckoutTests(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def checkout(self, **extra):
        return self.client.post(reverse("checkout"), {**GOOD_CHECKOUT, **extra})

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("checkout")).status_code, 302)

    def test_empty_cart_redirects(self):
        self.assertRedirects(self.client.get(reverse("checkout")), reverse("cart"))

    def test_valid_order_is_created(self):
        self.put_in_cart(self.p1, "A3", 2)          # 640 x 2
        r = self.checkout()
        o = Order.objects.get()
        self.assertRedirects(r, reverse("invoice", args=[o.pk]))
        self.assertEqual((o.user, o.total, o.discount_amount, o.phone), (self.user, 1280, 0, "+919876543210"))
        item = o.items.get()
        self.assertEqual((item.poster, item.size, item.qty, item.price), (self.p1, "A3", 2, 640))
        self.assertEqual(self.cart_lines(), {})

    def test_invalid_fields_create_no_order_and_show_errors(self):
        self.put_in_cart()
        for bad in ({"phone": "not-a-phone"}, {"phone": "123"}, {"payment": "HACKED"}, {"address": "x"}, {"name": ""}):
            r = self.checkout(**bad)
            self.assertEqual(r.status_code, 200, bad)
            self.assertTrue(r.context["form"].errors, bad)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.post(reverse("checkout"), {"action": "place_order"}).status_code, 200)

    def test_form_keeps_what_was_typed(self):
        self.put_in_cart()
        r = self.checkout(phone="bad")
        self.assertContains(r, "Test User")

    def test_inactive_poster_cannot_be_ordered(self):
        CartItem.objects.create(user=self.user, poster=self.hidden, size="A4")
        self.assertRedirects(self.checkout(), reverse("cart"))
        self.assertEqual(Order.objects.count(), 0)

    def test_confirmation_email_goes_to_the_customer(self):
        self.put_in_cart(); self.checkout()
        self.assertEqual([m.to for m in mail.outbox], [["buyer@example.com"]])

    def test_no_email_without_address_and_mail_failure_does_not_break_order(self):
        self.put_in_cart(); self.user.email = ""; self.user.save(); self.checkout()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Order.objects.count(), 1)
        self.user.email = "buyer@example.com"; self.user.save(); self.put_in_cart()
        with mock.patch("shop.views.send_mail", side_effect=OSError("smtp down")):
            r = self.checkout()
        self.assertEqual(r.status_code, 302)
        self.assertIn("/invoice/", r["Location"])
        self.assertEqual(Order.objects.count(), 2)

    def test_failure_midway_leaves_no_partial_order(self):
        Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        self.put_in_cart(); self.client.post(reverse("checkout"), {"action": "apply_coupon", "coupon_code": "TEN"})
        with mock.patch("shop.views.OrderItem.objects.bulk_create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Coupon.objects.get(code="TEN").times_used, 0)
        self.assertEqual(self.cart_lines(), {f"{self.p1.pk}:A4": 1})     # nothing lost, the customer can retry


class CouponTests(Base):
    def setUp(self):
        super().setUp()
        self.login()
        self.put_in_cart(self.p2, "A4", 1)   # total 500

    def apply(self, code):
        return self.client.post(reverse("checkout"), {"action": "apply_coupon", "coupon_code": code}, follow=True)

    def test_percent_coupon_discounts_and_counts_use(self):
        c = Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        self.apply("ten")
        r = self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        o = Order.objects.get()
        self.assertEqual((o.total, o.discount_amount, o.coupon_code), (450, 50, "TEN"))
        c.refresh_from_db(); self.assertEqual(c.times_used, 1)

    def test_flat_coupon_never_exceeds_cart_total(self):
        Coupon.objects.create(code="BIG", title="t", kind="flat", value=900)
        self.apply("BIG"); self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        self.assertEqual(Order.objects.get().total, 0)

    def test_unknown_expired_inactive_and_minimum_are_rejected(self):
        today = timezone.localdate()
        Coupon.objects.create(code="OLD", title="t", value=10, valid_until=today - timedelta(days=1))
        Coupon.objects.create(code="OFF", title="t", value=10, active=False)
        Coupon.objects.create(code="MIN", title="t", value=10, min_total=5000)
        for code in ("NOPE", "OLD", "OFF", "MIN"):
            self.apply(code)
            self.assertNotIn("coupon_code", self.client.session, code)

    def test_usage_limit_is_enforced(self):
        Coupon.objects.create(code="ONE", title="t", value=10, max_uses=1, times_used=1)
        self.apply("ONE")
        self.assertNotIn("coupon_code", self.client.session)

    def test_welcome_coupon_is_first_order_only(self):
        Coupon.objects.create(code="WELCOME15", title="t", value=15, first_order_only=True)
        self.apply("WELCOME15")
        self.assertEqual(self.client.session["coupon_code"], "WELCOME15")
        self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        self.assertEqual(Order.objects.get().discount_amount, 75)
        self.put_in_cart(self.p2, "A4", 1)
        self.apply("WELCOME15")
        self.assertNotIn("coupon_code", self.client.session)

    def test_cancelled_first_order_does_not_use_up_the_welcome_coupon(self):
        Coupon.objects.create(code="WELCOME15", title="t", value=15, first_order_only=True)
        self.make_order(status="Cancelled")
        self.apply("WELCOME15")
        self.assertEqual(self.client.session["coupon_code"], "WELCOME15")

    def test_coupon_that_stops_being_valid_before_placing_is_not_applied(self):
        c = Coupon.objects.create(code="ONE", title="t", value=10, max_uses=1)
        self.apply("ONE")
        Coupon.objects.filter(pk=c.pk).update(times_used=1)     # someone else used the last one
        r = self.client.post(reverse("checkout"), GOOD_CHECKOUT, follow=True)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(r.status_code, 200)


class ReviewTests(Base):
    def setUp(self):
        super().setUp()
        self.login()
        self.url = reverse("detail", args=[self.p1.pk])

    def post(self, rating, text="Lovely"):
        return self.client.post(self.url, {"rating": rating, "text": text})

    def test_only_buyers_can_review(self):
        self.post(5)
        self.assertEqual(Review.objects.count(), 0)

    def test_cancelled_order_does_not_count(self):
        self.make_order(status="Cancelled"); self.post(5)
        self.assertEqual(Review.objects.count(), 0)

    def test_valid_rating_is_saved_once(self):
        self.make_order(); self.post(4); self.post(1)
        self.assertEqual(list(Review.objects.values_list("rating", flat=True)), [4])

    def test_bad_ratings_are_rejected_without_crashing(self):
        self.make_order()
        for bad in ("abc", "0", "6", "99", "-3", ""):
            r = self.post(bad)
            self.assertEqual(r.status_code, 302, bad)
        self.assertEqual(Review.objects.count(), 0)

    def test_database_refuses_out_of_range_rating(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(poster=self.p1, user=self.user, rating=9, text="x")

    def test_review_text_is_escaped(self):
        self.make_order(); self.post(5, "<script>alert(1)</script>")
        self.assertNotContains(self.client.get(self.url), "<script>alert(1)</script>")


class LikeTests(Base):
    def setUp(self):
        super().setUp()
        self.review = Review.objects.create(poster=self.p1, user=self.other, rating=5, text="Great")
        self.url = reverse("review_like", args=[self.review.pk])

    def test_like_and_unlike(self):
        self.login()
        self.client.post(self.url); self.assertEqual(self.review.likes.count(), 1)
        self.client.post(self.url); self.assertEqual(self.review.likes.count(), 0)

    def test_cannot_like_own_review(self):
        self.login(self.other); self.client.post(self.url)
        self.assertEqual(self.review.likes.count(), 0)

    def test_anonymous_and_get_are_refused(self):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertEqual(self.review.likes.count(), 0)
        self.login(); self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_unsafe_redirect_target_is_ignored(self):
        self.login()
        r = self.client.post(self.url, {"next": "http://evil.example/x"})
        self.assertEqual(r["Location"], "/#reviews")

    def test_hidden_review_cannot_be_liked(self):
        self.review.is_approved = False; self.review.save(); self.login()
        self.assertEqual(self.client.post(self.url).status_code, 404)

    def test_most_liked_review_comes_first_on_home(self):
        third = User.objects.create_user("third", "t@example.com", PW)
        low = Review.objects.create(poster=self.p2, user=third, rating=5, text="Fine one")
        low.likes.add(self.user, self.staff)
        r = self.client.get(reverse("home"))
        self.assertEqual([x.pk for x in r.context["top_reviews"]], [low.pk, self.review.pk])


class WishlistTests(Base):
    def setUp(self):
        super().setUp(); self.login()

    def test_toggle(self):
        url = reverse("wish_toggle", args=[self.p1.pk])
        self.client.post(url); self.assertTrue(Wishlist.objects.filter(user=self.user, poster=self.p1).exists())
        self.client.post(url); self.assertFalse(Wishlist.objects.exists())

    def test_unknown_or_hidden_poster_gives_404_not_500(self):
        self.assertEqual(self.client.post(reverse("wish_toggle", args=[99999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("wish_toggle", args=[self.hidden.pk])).status_code, 404)


class VisibilityAndPermissionTests(Base):
    def test_hidden_poster_is_404_for_customers_but_visible_to_staff(self):
        url = reverse("detail", args=[self.hidden.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login(); self.assertEqual(self.client.get(url).status_code, 404)
        self.login(self.staff); self.assertEqual(self.client.get(url).status_code, 200)

    def test_hidden_poster_not_on_home_or_in_deck(self):
        r = self.client.get(reverse("home"))
        self.assertNotIn(self.hidden, list(r.context["posters"]))
        self.assertNotIn(self.hidden, r.context["deck"])

    def test_customer_pages_require_login(self):
        for name in ("checkout", "orders", "wishlist", "profile"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/accounts/login/", r["Location"])

    def test_staff_panel_is_staff_only(self):
        urls = [reverse(n) for n in ("admin_dashboard", "admin_orders", "admin_posters", "admin_coupons")]
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 302, u)           # anonymous
        self.login()
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 302, u)           # customer
        self.login(self.staff)
        for u in urls:
            self.assertEqual(self.client.get(u).status_code, 200, u)           # staff

    def test_registration_needs_an_email(self):
        data = {"username": "newbie", "password1": PW, "password2": PW}
        self.assertEqual(self.client.post(reverse("register"), data).status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())
        self.client.post(reverse("register"), {**data, "email": "new@example.com"})
        self.assertEqual(User.objects.get(username="newbie").email, "new@example.com")


class HomePageTests(Base):
    def test_pagination_and_filters(self):
        Poster.objects.bulk_create([
            Poster(title=f"Print {i:02d}", artist="X", category=self.cat, base_price=100 + i) for i in range(27)
        ])
        r = self.client.get(reverse("home"))
        self.assertEqual(len(r.context["posters"]), 12)
        self.assertEqual(r.context["page_obj"].paginator.num_pages, 3)
        self.assertContains(r, "page=2")
        self.assertEqual(len(self.client.get(reverse("home"), {"page": 3}).context["posters"]), 5)
        self.assertEqual(self.client.get(reverse("home"), {"page": 999}).status_code, 200)
        self.assertEqual(self.client.get(reverse("home"), {"page": "abc"}).status_code, 200)
        r = self.client.get(reverse("home"), {"q": "Print 0", "sort": "lo"})
        self.assertIn("q=Print+0", r.context["page_qs"])

    def test_query_count_does_not_grow_with_catalogue_size(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("home"))
            return len(ctx)
        cache.clear(); small = count()
        Poster.objects.bulk_create([Poster(title=f"P{i}", artist="X", category=self.cat, base_price=100) for i in range(40)])
        cache.clear(); self.assertLessEqual(count(), small + 1)

    def test_best_seller_sits_in_the_centre_and_cancelled_sales_do_not_count(self):
        self.make_order(poster=self.p2, qty=5)
        self.make_order(poster=self.p1, qty=2)
        self.make_order(poster=self.hidden, qty=50)
        self.make_order(poster=self.p1, qty=40, status="Cancelled")
        deck = self.client.get(reverse("home")).context["deck"]
        self.assertEqual(deck[len(deck) // 2], self.p2)
        self.assertNotIn(self.hidden, deck)

    def test_rating_average_ignores_hidden_reviews(self):
        Review.objects.create(poster=self.p1, user=self.user, rating=5, text="ok")
        Review.objects.create(poster=self.p1, user=self.other, rating=1, text="spam", is_approved=False)
        posters = {p.pk: p for p in self.client.get(reverse("home")).context["posters"]}
        self.assertEqual(posters[self.p1.pk].avg, 5)

    def test_no_invented_claims_and_real_promo_and_rating(self):
        html = self.client.get(reverse("home")).content.decode()
        for fake in ("43,000", "Buy 4 Get 3", "4.9/5"):
            self.assertNotIn(fake, html)
        self.assertNotIn("Use code", html)
        cache.clear()
        Coupon.objects.create(code="SAVE10", title="10% off", value=10)
        Review.objects.create(poster=self.p1, user=self.user, rating=4, text="ok")
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Use code SAVE10", html)
        self.assertIn("Rated 4.0/5 from 1 customer review", html)


class RegistrationEmailTests(Base):
    DATA = {"username": "newbie", "password1": PW, "password2": PW}

    def register(self, **extra):
        return self.client.post(reverse("register"), {**self.DATA, **extra})

    def test_email_already_used_is_rejected(self):
        r = self.register(email="buyer@example.com")          # belongs to the 'buyer' test user
        self.assertEqual(r.status_code, 200)
        self.assertIn("already exists", str(r.context["form"].errors["email"]))
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_check_ignores_letter_case_and_spaces(self):
        for variant in ("BUYER@EXAMPLE.COM", "  Buyer@Example.com  "):
            self.register(email=variant)
        self.assertEqual(User.objects.filter(email__iexact="buyer@example.com").count(), 1)

    def test_new_email_is_saved_in_lowercase(self):
        self.register(email="  New.Person@Example.COM ")
        self.assertEqual(User.objects.get(username="newbie").email, "new.person@example.com")

    def test_second_signup_with_the_same_new_email_is_rejected(self):
        self.register(email="fresh@example.com")
        self.client.logout()
        r = self.register(username="newbie2", email="FRESH@example.com")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie2").exists())

    def test_accounts_without_an_email_do_not_block_signups(self):
        User.objects.create_user("legacy1", "", PW); User.objects.create_user("legacy2", "", PW)
        self.assertEqual(self.register(email="ok@example.com").status_code, 302)

    def test_invalid_email_is_rejected(self):
        self.assertEqual(self.register(email="not-an-email").status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())


class StaffOrderTests(Base):
    def setUp(self):
        super().setUp()
        self.login(self.staff)

    def order_with(self, coupon=None, status="Processing"):
        o = Order.objects.create(user=self.user, name="n", address="a", phone="12345678", payment="Cash on delivery",
                                 total=900, status=status, coupon_code=coupon.code if coupon else "")
        a = OrderItem.objects.create(order=o, poster=self.p1, size="A4", qty=1, price=400)
        b = OrderItem.objects.create(order=o, poster=self.p2, size="A4", qty=1, price=500)
        if coupon:
            o.discount_amount = round(900 * coupon.value / 100) if coupon.kind == "percent" else min(coupon.value, 900)
            o.total = 900 - o.discount_amount; o.save()
        return o, a, b

    def set_qty(self, o, item, qty):
        return self.client.post(reverse("admin_order_detail", args=[o.pk]), {"action": "save_qty", f"qty-{item.pk}": qty})

    def test_quantity_edit_updates_the_total(self):
        o, a, b = self.order_with()
        self.set_qty(o, a, 3)
        o.refresh_from_db()
        self.assertEqual((o.total, o.discount_amount), (1700, 0))

    def test_quantity_edit_recalculates_percent_and_flat_discounts(self):
        pct = Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        o, a, b = self.order_with(pct)
        self.set_qty(o, a, 3); o.refresh_from_db()
        self.assertEqual((o.discount_amount, o.total), (170, 1530))
        flat = Coupon.objects.create(code="FLAT", title="t", kind="flat", value=100)
        o2, a2, b2 = self.order_with(flat)
        self.set_qty(o2, a2, 2); o2.refresh_from_db()
        self.assertEqual((o2.discount_amount, o2.total), (100, 1200))

    def test_odd_quantities_are_handled(self):
        o, a, b = self.order_with()
        self.set_qty(o, a, "abc"); a.refresh_from_db(); self.assertEqual(a.qty, 1)
        self.set_qty(o, a, 0); a.refresh_from_db(); self.assertEqual(a.qty, 1)
        self.set_qty(o, a, 5000); a.refresh_from_db(); self.assertEqual(a.qty, 99)

    def test_quantities_are_locked_once_an_order_has_shipped(self):
        o, a, b = self.order_with(status="Shipped")
        self.set_qty(o, a, 5); o.refresh_from_db(); a.refresh_from_db()
        self.assertEqual((a.qty, o.total), (1, 900))

    def test_status_cannot_go_backwards_or_skip(self):
        o, a, b = self.order_with(status="Delivered")
        url = reverse("admin_order_detail", args=[o.pk])
        self.client.post(url, {"action": "update_status", "status": "Processing"})
        o.refresh_from_db(); self.assertEqual(o.status, "Delivered")
        p, _, _ = self.order_with()
        self.client.post(reverse("admin_order_detail", args=[p.pk]), {"action": "update_status", "status": "Delivered"})
        p.refresh_from_db(); self.assertEqual(p.status, "Processing")

    def test_normal_flow_and_cancelled_is_final(self):
        o, a, b = self.order_with()
        url = reverse("admin_order_detail", args=[o.pk])
        for step in ("Shipped", "Delivered"):
            self.client.post(url, {"action": "update_status", "status": step}); o.refresh_from_db()
            self.assertEqual(o.status, step)
        c, _, _ = self.order_with(status="Cancelled")
        self.client.post(reverse("admin_order_detail", args=[c.pk]), {"action": "update_status", "status": "Processing"})
        c.refresh_from_db(); self.assertEqual(c.status, "Cancelled")

    def test_status_change_from_the_orders_list(self):
        o, a, b = self.order_with()
        self.client.post(reverse("admin_orders"), {"order_id": o.pk, "status": "Shipped"})
        o.refresh_from_db(); self.assertEqual(o.status, "Shipped")
        self.client.post(reverse("admin_orders"), {"order_id": o.pk, "status": "Processing"})
        o.refresh_from_db(); self.assertEqual(o.status, "Shipped")


class CancelReleasesCouponTests(Base):
    def setUp(self):
        super().setUp()
        self.coupon = Coupon.objects.create(code="LIMITED", title="t", value=10, max_uses=1, times_used=1)
        self.order = Order.objects.create(user=self.user, name="n", address="a", phone="12345678",
                                          payment="Cash on delivery", total=450, coupon_code="LIMITED")

    def used(self):
        self.coupon.refresh_from_db(); return self.coupon.times_used

    def test_customer_cancel_gives_the_use_back_once(self):
        self.login()
        self.client.post(reverse("cancel", args=[self.order.pk])); self.assertEqual(self.used(), 0)
        self.client.post(reverse("cancel", args=[self.order.pk])); self.assertEqual(self.used(), 0)
        self.assertTrue(self.coupon.is_available())

    def test_staff_cancel_gives_the_use_back_once(self):
        self.login(self.staff)
        url = reverse("admin_order_detail", args=[self.order.pk])
        self.client.post(url, {"action": "cancel"}); self.assertEqual(self.used(), 0)
        self.client.post(url, {"action": "update_status", "status": "Cancelled"}); self.assertEqual(self.used(), 0)

    def test_counter_never_goes_below_zero(self):
        Coupon.objects.filter(pk=self.coupon.pk).update(times_used=0)
        self.login(); self.client.post(reverse("cancel", args=[self.order.pk]))
        self.assertEqual(self.used(), 0)


class UserAdminTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.boss = User.objects.create_superuser("boss", "boss@example.com", PW)
        cls.boss2 = User.objects.create_superuser("boss2", "boss2@example.com", PW)

    def toggle(self, user, what):
        return self.client.post(reverse("admin_users"), {"user_id": user.pk, "toggle": what})

    def test_superuser_cannot_lock_themselves_out(self):
        self.login(self.boss)
        self.toggle(self.boss, "active"); self.toggle(self.boss, "staff")
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_active and self.boss.is_staff)

    def test_superusers_staff_flag_is_protected_but_normal_users_can_be_changed(self):
        self.login(self.boss)
        self.toggle(self.boss2, "staff"); self.boss2.refresh_from_db(); self.assertTrue(self.boss2.is_staff)
        self.toggle(self.other, "active"); self.other.refresh_from_db(); self.assertFalse(self.other.is_active)
        self.toggle(self.other, "staff"); self.other.refresh_from_db(); self.assertTrue(self.other.is_staff)

    def test_ordinary_staff_cannot_manage_users(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("admin_users")).status_code, 302)
        self.toggle(self.other, "active"); self.other.refresh_from_db(); self.assertTrue(self.other.is_active)

    def test_cancelled_orders_do_not_count_as_money_spent(self):
        Order.objects.create(user=self.other, name="n", address="a", phone="12345678", payment="Cash on delivery", total=50)
        Order.objects.create(user=self.other, name="n", address="a", phone="12345678", payment="Cash on delivery", total=100, status="Cancelled")
        self.login(self.boss)
        users = {u.pk: u for u in self.client.get(reverse("admin_users")).context["users"]}
        self.assertEqual(users[self.other.pk].total_spent, 50)


def png_bytes(w, h):
    buf = BytesIO()
    Image.linear_gradient("L").resize((w, h)).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


class ImageTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls.media); cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable(); shutil.rmtree(cls.media, ignore_errors=True)
        super().tearDownClass()

    def upload(self, data, name="art.png", ctype="image/png", **extra):
        self.login(self.staff)
        return self.client.post(reverse("admin_posters"), {
            "title": "Uploaded", "artist": "X", "category": self.cat.pk, "description": "", "base_price": 300,
            "hue": 200, "is_active": "on", "image": SimpleUploadedFile(name, data, ctype), **extra})

    def test_big_upload_is_resized_and_compressed(self):
        data = png_bytes(3000, 2000)
        self.upload(data)
        p = Poster.objects.get(title="Uploaded")
        with Image.open(p.image.path) as im:
            self.assertLessEqual(max(im.size), images.MAX_SIDE)
            self.assertEqual(im.format, "JPEG")
        self.assertTrue(p.image.name.endswith(".jpg"))
        self.assertLess(p.image.size, len(data))

    def jpeg(self, quality, size=(300, 400)):
        buf = BytesIO(); Image.linear_gradient("L").resize(size).convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        return buf.getvalue()

    def test_small_image_that_is_already_tiny_is_kept_as_is(self):
        original = self.jpeg(5)     # re-encoding at normal quality would only make it bigger
        self.upload(original, "tiny.jpg", "image/jpeg")
        self.assertEqual(Poster.objects.get(title="Uploaded").image.size, len(original))

    def test_small_images_are_never_made_bigger_or_resized(self):
        original = self.jpeg(95)
        self.upload(original, "ok.jpg", "image/jpeg")
        p = Poster.objects.get(title="Uploaded")
        self.assertLessEqual(p.image.size, len(original))
        with Image.open(p.image.path) as im:
            self.assertEqual(im.size, (300, 400))

    def test_oversize_file_is_rejected(self):
        with mock.patch.object(images, "MAX_UPLOAD_BYTES", 1000):
            r = self.upload(png_bytes(400, 400))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Poster.objects.filter(title="Uploaded").exists())

    def test_too_many_pixels_is_rejected(self):
        with mock.patch.object(images, "MAX_PIXELS", 100):
            self.upload(png_bytes(400, 400))
        self.assertFalse(Poster.objects.filter(title="Uploaded").exists())

    def test_not_an_image_is_rejected(self):
        self.upload(b"just text", "fake.png")
        self.assertFalse(Poster.objects.filter(title="Uploaded").exists())

    def test_shrink_images_command_fixes_old_uploads(self):
        name = default_storage.save("posters/legacy.png", ContentFile(png_bytes(3000, 2000)))
        Poster.objects.bulk_create([Poster(title="Legacy", artist="L", category=self.cat, base_price=100, image=name)])
        call_command("shrink_images", "--dry-run", stdout=BytesIO().__class__ and open(os.devnull, "w"))
        self.assertTrue(default_storage.exists(name))
        self.assertEqual(Poster.objects.get(title="Legacy").image.name, name)
        call_command("shrink_images", stdout=open(os.devnull, "w"))
        p = Poster.objects.get(title="Legacy")
        self.assertTrue(p.image.name.endswith(".jpg"))
        self.assertFalse(default_storage.exists(name))
        with Image.open(p.image.path) as im:
            self.assertLessEqual(max(im.size), images.MAX_SIDE)


class SettingsSafetyTests(SimpleTestCase):
    """The settings module is read once at start-up, so each case runs in a fresh Python process."""
    LONG_KEY = "k" * 50

    def load(self, env=None, argv0="gunicorn"):
        clean = {k: v for k, v in os.environ.items()
                 if k not in {"DEBUG", "SECRET_KEY", "ALLOWED_HOSTS", "DB_ENGINE", "EMAIL_BACKEND",
                              "BEHIND_PROXY", "DJANGO_SETTINGS_MODULE", "CSRF_TRUSTED_ORIGINS"}}
        clean.update(env or {})
        code = (f"import sys; sys.argv = [{argv0!r}]\n"
                "import posterhub.settings as s\n"
                "print(s.DEBUG, s.ALLOWED_HOSTS, getattr(s, 'SECURE_SSL_REDIRECT', False), "
                "getattr(s, 'SESSION_COOKIE_SECURE', False), s.EMAIL_BACKEND.rsplit('.', 2)[-2])\n")
        return subprocess.run([sys.executable, "-c", code], env=clean, cwd=settings.BASE_DIR,
                              capture_output=True, text=True)

    def test_production_refuses_to_start_without_a_real_secret_key(self):
        r = self.load()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SECRET_KEY", r.stderr)

    def test_weak_or_old_default_keys_are_refused(self):
        for key in ("dev-only-change-me", "django-insecure-" + "x" * 50, "short"):
            r = self.load({"SECRET_KEY": key, "ALLOWED_HOSTS": "shop.example.com"})
            self.assertNotEqual(r.returncode, 0, key)

    def test_production_refuses_to_start_without_allowed_hosts(self):
        r = self.load({"SECRET_KEY": self.LONG_KEY})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ALLOWED_HOSTS", r.stderr)

    def test_properly_configured_production_is_locked_down(self):
        r = self.load({"SECRET_KEY": self.LONG_KEY, "ALLOWED_HOSTS": "shop.example.com, www.example.com"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(" ", 1)[0], "False")
        self.assertIn("['shop.example.com', 'www.example.com'] True True smtp", r.stdout)

    def test_manage_py_starts_in_development_mode_on_localhost_only(self):
        r = self.load(argv0="manage.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "True [] False False console")

    def test_debug_can_be_forced_off_even_with_manage_py(self):
        r = self.load({"DEBUG": "0"}, argv0="manage.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SECRET_KEY", r.stderr)

    def test_debug_can_be_forced_on_elsewhere(self):
        r = self.load({"DEBUG": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("True"))


class SeedSafetyTests(TestCase):
    def seed(self, *args):
        call_command("seed", *args, stdout=open(os.devnull, "w"))

    def test_no_default_admin_outside_development(self):
        self.seed()           # the test runner always runs with DEBUG off
        self.assertFalse(User.objects.filter(username="admin").exists())
        self.assertTrue(Poster.objects.exists())
        self.assertTrue(Coupon.objects.filter(code="WELCOME15", first_order_only=True).exists())

    @override_settings(DEBUG=True)
    def test_development_still_gets_the_easy_admin(self):
        self.seed()
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_superuser and admin.check_password("admin123"))

    def test_admin_password_can_be_supplied(self):
        self.seed("--admin-password", "Sturdy-Pass-7391")
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_superuser and admin.check_password("Sturdy-Pass-7391"))

    def test_weak_admin_password_is_rejected_before_anything_is_created(self):
        for weak in ("admin123", "short", "12345678"):
            with self.assertRaises(CommandError):
                self.seed("--admin-password", weak)
        self.assertFalse(User.objects.filter(username="admin").exists())
        self.assertFalse(Poster.objects.exists())

    def test_existing_admin_is_never_touched(self):
        User.objects.create_superuser("admin", "a@example.com", "Original-Pass-1234")
        self.seed("--admin-password", "Different-Pass-5678")
        self.assertTrue(User.objects.get(username="admin").check_password("Original-Pass-1234"))

    def test_running_seed_twice_is_harmless(self):
        self.seed(); self.seed()
        self.assertEqual(Coupon.objects.filter(code="WELCOME15").count(), 1)


class AccountVaultTests(Base):
    def lines(self, user):
        return {f"{i.poster_id}:{i.size}": i.qty for i in CartItem.objects.filter(user=user)}

    def add(self, client, poster, size="A4"):
        client.post(reverse("cart_add"), {"poster": poster.pk, "size": size})

    def count(self, client):
        return client.get(reverse("home")).context["cart_count"]

    def test_each_account_has_its_own_vault_on_the_same_browser(self):
        self.login(self.user); self.add(self.client, self.p1); self.add(self.client, self.p1)
        self.assertEqual(self.count(self.client), 2)
        self.client.post(reverse("logout"))
        self.assertEqual(self.count(self.client), 0)                    # nothing is left behind for the next person
        self.login(self.other)
        self.assertEqual(self.count(self.client), 0)                    # another customer starts with an empty Vault
        self.add(self.client, self.p2)
        self.assertEqual(self.count(self.client), 1)
        self.client.post(reverse("logout")); self.login(self.user)
        self.assertEqual(self.count(self.client), 2)                    # the first customer's Vault is back
        self.assertEqual(self.lines(self.other), {f"{self.p2.pk}:A4": 1})

    def test_vault_follows_the_account_to_another_browser(self):
        self.login(self.user); self.add(self.client, self.p1, "A3")
        phone = Client(); phone.force_login(self.user)
        self.assertEqual(phone.get(reverse("cart")).context["total"], 640)
        self.assertEqual(Client().get(reverse("cart")).context["total"], 0)   # a stranger sees nothing

    def test_sign_out_clears_the_coupon_too(self):
        self.login(); self.put_in_cart()
        self.client.post(reverse("checkout"), {"action": "apply_coupon", "coupon_code": "NOPE"})
        s = self.client.session; s["coupon_code"] = "WELCOME15"; s.save()
        self.client.post(reverse("logout"))
        self.assertNotIn("coupon_code", self.client.session)

    def test_items_added_before_signing_in_are_merged_into_the_account(self):
        CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=19)
        for poster, size in ((self.p1, "A4"), (self.p1, "A4"), (self.p2, "A2")):
            self.add(self.client, poster, size)                         # signed out: stored in the browser
        self.assertEqual(self.count(self.client), 3)
        self.login(self.user)
        self.assertEqual(self.lines(self.user), {f"{self.p1.pk}:A4": 20, f"{self.p2.pk}:A2": 1})   # 19 + 2, capped at 20
        self.assertNotIn("cart", self.client.session)

    def test_a_cart_left_in_the_session_is_moved_to_the_signed_in_account(self):
        self.login(self.user)
        s = self.client.session; s["cart"] = {f"{self.p1.pk}:A4": 2}; s.save()
        self.assertEqual(self.count(self.client), 2)
        self.assertEqual(self.lines(self.user), {f"{self.p1.pk}:A4": 2})
        self.assertNotIn("cart", self.client.session)

    def test_hidden_posters_are_ignored_but_their_line_is_kept(self):
        CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=2)
        CartItem.objects.create(user=self.user, poster=self.p2, size="A4", qty=1)
        self.login(self.user)
        self.assertEqual(self.count(self.client), 3)
        Poster.objects.filter(pk=self.p2.pk).update(is_active=False)
        self.assertEqual(self.count(self.client), 2)
        self.assertEqual([i["poster"] for i in self.client.get(reverse("cart")).context["items"]], [self.p1])
        Poster.objects.filter(pk=self.p2.pk).update(is_active=True)
        self.assertEqual(self.count(self.client), 3)

    def test_one_customer_cannot_change_another_customers_lines(self):
        CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=2)
        self.login(self.other)
        self.client.post(reverse("cart_update"), {"key": f"{self.p1.pk}:A4", "action": "del"})
        self.assertEqual(self.lines(self.user), {f"{self.p1.pk}:A4": 2})

    def test_update_remove_and_cap_work_on_the_saved_vault(self):
        self.login(); self.add(self.client, self.p1)
        key = f"{self.p1.pk}:A4"
        self.client.post(reverse("cart_update"), {"key": key, "action": "inc"}); self.assertEqual(self.lines(self.user)[key], 2)
        self.client.post(reverse("cart_update"), {"key": key, "action": "dec"}); self.assertEqual(self.lines(self.user)[key], 1)
        self.client.post(reverse("cart_update"), {"key": key, "action": "dec"}); self.assertEqual(self.lines(self.user), {})
        CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=20)
        self.add(self.client, self.p1); self.assertEqual(self.lines(self.user)[key], 20)

    def test_ordering_empties_only_the_buyers_vault(self):
        CartItem.objects.create(user=self.other, poster=self.p2, size="A4", qty=1)
        CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=1)
        self.login(); self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        self.assertEqual(self.lines(self.user), {})
        self.assertEqual(self.lines(self.other), {f"{self.p2.pk}:A4": 1})

    def test_deleting_an_account_removes_its_vault(self):
        CartItem.objects.create(user=self.other, poster=self.p1, size="A4", qty=1)
        self.other.delete()
        self.assertEqual(CartItem.objects.count(), 0)

    def test_database_rules(self):
        for bad_qty in (0, 21):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=bad_qty)
        CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(user=self.user, poster=self.p1, size="A4", qty=1)


class InvoiceAndOrderHistoryTests(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def place(self, poster=None, size="A3", qty=2, coupon_code=""):
        """Place a real order through checkout and return it."""
        self.put_in_cart(poster or self.p1, size, qty)
        if coupon_code:
            self.client.post(reverse("checkout"), {"action": "apply_coupon", "coupon_code": coupon_code})
        self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        return Order.objects.filter(user=self.user).latest("pk")

    def invoice(self, order, client=None):
        return (client or self.client).get(reverse("invoice", args=[order.pk]))

    # ---- invoice
    def test_checkout_lands_on_the_invoice_with_everything_on_it(self):
        self.put_in_cart(self.p1, "A3", 2)
        r = self.client.post(reverse("checkout"), GOOD_CHECKOUT, follow=True)
        o = Order.objects.get()
        self.assertEqual(r.redirect_chain[-1][0], reverse("invoice", args=[o.pk]))
        for text in (o.invoice_number, "Alpha", "A3", "₹640", "₹1280", "Test User", "12 MG Road", "+919876543210",
                     "buyer@example.com", "Cash on delivery", "Pay ₹1280 in cash"):
            self.assertContains(r, text)

    def test_invoice_shows_the_coupon_discount(self):
        Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        o = self.place(coupon_code="TEN")
        self.assertEqual((o.discount_amount, o.total), (128, 1152))
        r = self.invoice(o)
        for text in ("Subtotal", "₹1280", "Discount (TEN)", "₹128", "₹1152"):
            self.assertContains(r, text)

    def test_only_the_owner_or_staff_can_open_an_invoice(self):
        o = self.place()
        self.assertEqual(self.invoice(o).status_code, 200)
        other = Client(); other.force_login(self.other)
        self.assertEqual(self.invoice(o, other).status_code, 404)
        self.assertEqual(self.invoice(o, Client()).status_code, 302)          # signed out: sent to log in
        boss = Client(); boss.force_login(self.staff)
        self.assertEqual(self.invoice(o, boss).status_code, 200)

    def test_cancelled_order_invoice_says_so(self):
        o = self.place(); o.change_status("Cancelled")
        self.assertContains(self.invoice(o), "This order was cancelled")

    def test_invoice_keeps_the_title_if_the_poster_is_renamed_or_deleted(self):
        o = self.place()
        self.assertEqual(o.items.get().title, "Alpha")
        Poster.objects.filter(pk=self.p1.pk).update(title="Renamed")
        self.assertContains(self.invoice(o), "Alpha")
        self.assertNotContains(self.invoice(o), "Renamed")
        self.p1.delete()
        self.assertIsNone(o.items.get().poster)
        self.assertContains(self.invoice(o), "Alpha")
        self.assertContains(self.client.get(reverse("orders")), "Alpha")

    def test_old_line_without_a_saved_title_still_reads_well(self):
        o = Order.objects.create(user=self.user, name="n", address="a", phone="12345678", payment="Cash on delivery", total=5)
        item = OrderItem.objects.create(order=o, poster=self.p2, size="A4", qty=1, price=5)
        self.assertEqual(item.display_title, "Beta")                       # falls back to the poster's title
        self.p2.delete()
        item.refresh_from_db()
        self.assertEqual(item.display_title, "Poster no longer available")

    def test_confirmation_email_carries_the_invoice_details(self):
        Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        o = self.place(coupon_code="TEN")
        body = mail.outbox[-1].body
        for text in (o.invoice_number, "Alpha (A3) x 2: ₹1280", "Subtotal: ₹1280", "Discount (TEN): -₹128",
                     "Total: ₹1152", "Cash on delivery", f"/orders/{o.pk}/invoice/"):
            self.assertIn(text, body)

    # ---- order history
    def test_orders_page_shows_full_details(self):
        Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        o = self.place(coupon_code="TEN")
        r = self.client.get(reverse("orders"))
        for text in (f"Order #{o.pk}", "Alpha", "2 &times; ₹640", "Shipping to", "Test User", "12 MG Road",
                     "Subtotal", "Discount (TEN)", "₹1152", "Cash on delivery", reverse("invoice", args=[o.pk]),
                     f"cancel-order-{o.pk}"):
            self.assertContains(r, text)

    def test_progress_tracker_follows_the_status(self):
        o = self.place()
        states = lambda: [s["state"] for s in Order.objects.get(pk=o.pk).timeline]
        self.assertEqual(states(), ["current", "todo", "todo"])
        o.change_status("Shipped"); self.assertEqual(states(), ["done", "current", "todo"])
        o.change_status("Delivered"); self.assertEqual(states(), ["done", "done", "done"])
        c = self.place(); c.change_status("Cancelled")
        self.assertEqual(Order.objects.get(pk=c.pk).timeline, [])
        self.assertContains(self.client.get(reverse("orders")), "This order was cancelled")

    def test_cancel_button_only_while_processing(self):
        o = self.place()
        self.assertContains(self.client.get(reverse("orders")), f"cancel-order-{o.pk}")
        o.change_status("Shipped")
        self.assertNotContains(self.client.get(reverse("orders")), f"cancel-order-{o.pk}")

    def test_only_my_orders_newest_first_and_cancelled_not_counted_as_spent(self):
        first = self.place(qty=1)                      # 640
        second = self.place(self.p2, "A4", 1)          # 500
        third = self.place(qty=1); third.change_status("Cancelled")
        theirs = Order.objects.create(user=self.other, name="x", address="y", phone="12345678", payment="Cash on delivery", total=99)
        r = self.client.get(reverse("orders"))
        self.assertEqual([o.pk for o in r.context["orders"]], [third.pk, second.pk, first.pk])
        self.assertNotIn(theirs.pk, [o.pk for o in r.context["orders"]])
        self.assertEqual((r.context["order_count"], r.context["total_spent"]), (3, 1140))

    def test_status_filter_and_tab_counts(self):
        a = self.place(); b = self.place(); b.change_status("Shipped"); c = self.place(); c.change_status("Cancelled")
        r = self.client.get(reverse("orders"), {"status": "Shipped"})
        self.assertEqual([o.pk for o in r.context["orders"]], [b.pk])
        self.assertEqual([(v, n) for v, _, n in r.context["tabs"]], [("", 3), ("Processing", 1), ("Shipped", 1), ("Delivered", 0), ("Cancelled", 1)])
        self.assertEqual(len(self.client.get(reverse("orders"), {"status": "nonsense"}).context["orders"]), 3)
        self.assertContains(self.client.get(reverse("orders"), {"status": "Delivered"}), "no delivered orders")

    def test_orders_are_paginated(self):
        for _ in range(12):
            Order.objects.create(user=self.user, name="n", address="a", phone="12345678", payment="Cash on delivery", total=1)
        r = self.client.get(reverse("orders"))
        self.assertEqual(len(r.context["orders"]), 10)
        self.assertEqual(len(self.client.get(reverse("orders"), {"page": 2}).context["orders"]), 2)
        self.assertEqual(self.client.get(reverse("orders"), {"page": 999}).status_code, 200)
        self.assertEqual(self.client.get(reverse("orders"), {"status": "Processing"}).context["page_qs"], "status=Processing")

    def test_orders_page_needs_login_and_handles_no_orders(self):
        self.assertContains(self.client.get(reverse("orders")), "No orders yet")
        self.assertEqual(Client().get(reverse("orders")).status_code, 302)

    def test_staff_order_page_uses_the_saved_title(self):
        o = self.place(); self.p1.delete()
        self.login(self.staff)
        self.assertContains(self.client.get(reverse("admin_order_detail", args=[o.pk])), "Alpha")

    def test_model_helpers(self):
        o = self.place(size="A3", qty=2)
        self.assertEqual(o.invoice_number, f"PH-{o.pk:06d}")
        self.assertEqual(o.items_subtotal, 1280)
        self.assertEqual(o.items.get().subtotal, 1280)

