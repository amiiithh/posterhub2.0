from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from shop.images import shrink
from shop.models import Poster


class Command(BaseCommand):
    help = "Shrink poster images that were uploaded before resizing existed (use --dry-run to preview)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without touching any file")

    def handle(self, *args, **opts):
        saved_total = changed = 0
        for p in Poster.objects.exclude(image=""):
            try:
                with default_storage.open(p.image.name, "rb") as fh:
                    before = fh.size if hasattr(fh, "size") else default_storage.size(p.image.name)
                    small = shrink(fh, p.image.name)
            except Exception as exc:   # missing or unreadable file: report and carry on
                self.stdout.write(self.style.WARNING(f"skip {p.title}: {exc}"))
                continue
            if small is None:
                continue
            saved = before - small.size
            self.stdout.write(f"{p.title}: {before // 1024} KB -> {small.size // 1024} KB")
            changed += 1; saved_total += saved
            if not opts["dry_run"]:
                old = p.image.name
                p.image.save(small.name, small, save=False)
                p.save(update_fields=["image"])
                if old != p.image.name:
                    default_storage.delete(old)
        verb = "Would save" if opts["dry_run"] else "Saved"
        self.stdout.write(self.style.SUCCESS(f"{verb} {saved_total // 1024} KB across {changed} image(s)."))
