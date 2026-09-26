"""Draw assets/app.ico: a teal rounded square with a white "LT"."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
TEAL = (0x36, 0x87, 0x77, 255)


def draw(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=TEAL)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.46))
    except OSError:
        font = ImageFont.load_default(size=int(size * 0.46))
    box = d.textbbox((0, 0), "LT", font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    d.text((x, y), "LT", font=font, fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    out = ROOT / "assets" / "app.ico"
    out.parent.mkdir(exist_ok=True)
    draw().save(out, sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    print(f"wrote {out}")
