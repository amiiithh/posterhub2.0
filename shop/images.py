"""Shrinks uploaded poster images so the site stays fast."""
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_SIDE = 1400          # longest side in pixels (plenty for the page, even on sharp screens)
QUALITY = 82             # JPEG quality
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 60_000_000  # refuse absurdly large images (also protects the server's memory)


def shrink(file_obj, name):
    """Return a smaller JPEG as a ContentFile, or None when the original is already small enough."""
    file_obj.seek(0)
    original_size = getattr(file_obj, "size", None)
    img = Image.open(file_obj)
    img = ImageOps.exif_transpose(img)
    resized = max(img.size) > MAX_SIDE
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        img = flat
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = BytesIO()
    img.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    data = out.getvalue()
    if not resized and original_size is not None and original_size <= len(data):
        return None   # already small: keep the original untouched
    return ContentFile(data, name=os.path.splitext(os.path.basename(name))[0] + ".jpg")
