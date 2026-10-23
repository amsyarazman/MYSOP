"""Validate and re-encode small square recipe photos; discard source metadata."""
import base64
import binascii
from io import BytesIO

from PIL import Image, UnidentifiedImageError


def square_photo(value):
    if value is None:
        return None
    prefix = 'data:image/jpeg;base64,'
    if not value.startswith(prefix):
        raise ValueError('Choose a photo with the photo upload control')
    try:
        raw = base64.b64decode(value[len(prefix):], validate=True)
        if len(raw) > 150_000:
            raise ValueError('Photo must be at most 150 KB')
        with Image.open(BytesIO(raw)) as image:
            w, h = image.size
            if image.format != 'JPEG' or w != h or not 1 <= w <= 512:
                raise ValueError('Photo must be a square JPEG up to 512 × 512 pixels')
            image.load()
            image = image.convert('RGB')
            for quality in (80, 65, 50, 35):
                output = BytesIO()
                image.save(output, format='JPEG', quality=quality, optimize=True)
                if len(output.getvalue()) <= 150_000:
                    break
            if len(output.getvalue()) > 150_000:
                raise ValueError('Could not compress this photo below 150 KB')
        return prefix + base64.b64encode(output.getvalue()).decode('ascii')
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Photo is not a valid compressed JPEG') from exc
