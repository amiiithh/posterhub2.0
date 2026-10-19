from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import Category, Coupon, Order, OrderItem, Poster, Review, Wishlist

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

    def login(self, user=None):
        self.client.force_login(user or self.user)

    def put_in_cart(self, poster=None, size="A4", qty=1):
        s = self.client.session
        s["cart"] = {f"{(poster or self.p1).pk}:{size}": qty}
        s.save()

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

    def test_corrupt_or_hidden_entries_are_dropped(self):
        s = self.client.session
        s["cart"] = {"garbage": 1, f"{self.p1.pk}:A9": 1, f"{self.hidden.pk}:A4": 1, f"{self.p2.pk}:A4": 2}
        s.save()
        r = self.client.get(reverse("cart"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.session["cart"], {f"{self.p2.pk}:A4": 2})
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
        self.assertRedirects(r, reverse("orders"))
        o = Order.objects.get()
        self.assertEqual((o.user, o.total, o.discount_amount, o.phone), (self.user, 1280, 0, "+919876543210"))
        item = o.items.get()
        self.assertEqual((item.poster, item.size, item.qty, item.price), (self.p1, "A3", 2, 640))
        self.assertEqual(self.client.session["cart"], {})

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
        s = self.client.session; s["cart"] = {f"{self.hidden.pk}:A4": 1}; s.save()
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
            self.assertRedirects(self.checkout(), reverse("orders"))
        self.assertEqual(Order.objects.count(), 2)

    def test_failure_midway_leaves_no_partial_order(self):
        Coupon.objects.create(code="TEN", title="t", kind="percent", value=10)
        self.put_in_cart(); self.client.post(reverse("checkout"), {"action": "apply_coupon", "coupon_code": "TEN"})
        with mock.patch("shop.views.OrderItem.objects.bulk_create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("checkout"), GOOD_CHECKOUT)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Coupon.objects.get(code="TEN").times_used, 0)


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
