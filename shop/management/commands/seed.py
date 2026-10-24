import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from shop.models import Category, Poster, Coupon

D = [("Last Reel","movies","Mira Odell","A noir cinema marquee glowing at midnight.",349,260),("Final Frame","movies","Jon Vasek","Minimal one-sheet for a heist thriller.",399,10),
("Spin Cycle","music","Dee Rao","Vinyl groove study in warm tones.",349,25),("Loud Hours","music","Kai Mendes","Gig-flyer style poster for live music.",379,330),
("Start Before Ready","motivational","Ana Pires","Bold type for a bold morning.",299,200),("One More Mile","motivational","Tom Reyes","Summit at sunrise.",329,18),
("Skyline Sprint","anime","Yuki Aoba","Speed lines over a neon rooftop.",449,310),("Moon Courier","anime","Hana Mori","A lantern messenger under a huge moon.",449,265),
("Pine Mist","nature","Lea Strand","Layered hills fading into fog.",329,150),("Tidal Hour","nature","Omar Ibe","Dusk over a calm bay.",329,195),
("Overlap No. 4","abstract","Ravi Nair","Translucent shapes in cold colour.",299,230),("Quiet Grid","abstract","Sol Ferro","Geometric calm in four tones.",299,45)]
class Command(BaseCommand):
    help = (
        "Create sample categories, posters and coupons. Also creates the 'admin' account: "
        "admin / admin123 in development only, otherwise pass --admin-password (or set ADMIN_PASSWORD)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--admin-password", help="Password for the 'admin' account (required outside development)")

    def handle(self, *a, **opts):
        password = opts.get("admin_password") or os.environ.get("ADMIN_PASSWORD")
        if password:
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError("Admin password rejected: " + " ".join(exc.messages))
        cats = {s: Category.objects.get_or_create(slug=s, defaults={"name": s.title()})[0] for s in {d[1] for d in D}}
        for t, c, ar, de, pr, h in D:
            Poster.objects.get_or_create(title=t, defaults=dict(category=cats[c], artist=ar, description=de, base_price=pr, hue=h))
        COUPONS = [
            dict(code="WELCOME15", title="15% off your first order", kind="percent", value=15, min_total=0, first_order_only=True),
            dict(code="STUDIO50", title="₹500 off orders above ₹2,500", kind="flat", value=500, min_total=2500),
            dict(code="FESTIVE25", title="25% off the festive wall upgrade", kind="percent", value=25, min_total=1500),
        ]
        for c in COUPONS:
            Coupon.objects.get_or_create(code=c["code"], defaults=c)
        if User.objects.filter(username="admin").exists():
            note = "The 'admin' account already exists and was left unchanged."
        elif password:
            User.objects.create_superuser("admin", "admin@posterhub.com", password)
            note = "Admin account 'admin' created with the password you supplied."
        elif settings.DEBUG:
            User.objects.create_superuser("admin", "admin@posterhub.com", "admin123")
            note = "Admin login (development only): admin / admin123"
        else:
            note = "No admin account created. Re-run with --admin-password, or use: python manage.py createsuperuser"
        self.stdout.write("Seeded. " + note)
