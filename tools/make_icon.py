"""生成财务管理软件图标：蓝色圆角底 + 白色上涨柱状图 + 货币符号。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for name in ("msyh.ttc", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=(37, 99, 235, 255)
    )

    unit = size / 256.0
    bar_w = int(38 * unit)
    gap = int(24 * unit)
    base_y = int(198 * unit)
    bars = [(70, 58), (116, 96), (162, 150)]
    for x, h in bars:
        top = base_y - int(h * unit)
        draw.rounded_rectangle(
            (int(x * unit), top, int(x * unit) + bar_w, base_y),
            radius=int(10 * unit),
            fill=(255, 255, 255, 255),
        )
    draw.rounded_rectangle(
        (int(38 * unit), int(214 * unit), int(218 * unit), int(224 * unit)),
        radius=int(5 * unit),
        fill=(255, 255, 255, 255),
    )

    symbol_size = int(52 * unit)
    font = _font(symbol_size)
    symbol = "¥"
    bbox = draw.textbbox((0, 0), symbol, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(
        ((size - text_w) / 2 - bbox[0], int(26 * unit) - bbox[1]),
        symbol,
        font=font,
        fill=(255, 255, 255, 255),
    )
    return img


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "app" / "assets" / "app_icon.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    icon = make_icon(256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(
        target,
        format="ICO",
        sizes=sizes,
    )
    print(f"icon saved: {target}")


if __name__ == "__main__":
    main()
