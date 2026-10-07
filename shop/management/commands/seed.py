from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from shop.models import Category, Poster
D = [("Last Reel","movies","Mira Odell","A noir cinema marquee glowing at midnight.",349,260),("Final Frame","movies","Jon Vasek","Minimal one-sheet for a heist thriller.",399,10),
("Spin Cycle","music","Dee Rao","Vinyl groove study in warm tones.",349,25),("Loud Hours","music","Kai Mendes","Gig-flyer style poster for live music.",379,330),
("Start Before Ready","motivational","Ana Pires","Bold type for a bold morning.",299,200),("One More Mile","motivational","Tom Reyes","Summit at sunrise.",329,18),
("Skyline Sprint","anime","Yuki Aoba","Speed lines over a neon rooftop.",449,310),("Moon Courier","anime","Hana Mori","A lantern messenger under a huge moon.",449,265),
("Pine Mist","nature","Lea Strand","Layered hills fading into fog.",329,150),("Tidal Hour","nature","Omar Ibe","Dusk over a calm bay.",329,195),
("Overlap No. 4","abstract","Ravi Nair","Translucent shapes in cold colour.",299,230),("Quiet Grid","abstract","Sol Ferro","Geometric calm in four tones.",299,45)]
class Command(BaseCommand):
    help = "Create sample categories, posters and an admin user (admin / admin123)"
    def handle(self, *a, **k):
        cats = {s: Category.objects.get_or_create(slug=s, defaults={"name": s.title()})[0] for s in {d[1] for d in D}}
        for t, c, ar, de, pr, h in D:
            Poster.objects.get_or_create(title=t, defaults=dict(category=cats[c], artist=ar, description=de, base_price=pr, hue=h))
        if not User.objects.filter(username="admin").exists(): User.objects.create_superuser("admin", "admin@posterhub.com", "admin123")
        self.stdout.write("Seeded. Admin login: admin / admin123")
