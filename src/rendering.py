from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def render_frame(
    color: Image.Image,
    gray: Image.Image,
    size: int,
    usage: float | None,
    healthy: bool,
    font: ImageFont.FreeTypeFont,
    *,
    missing_text: str = "--",
) -> Image.Image:
    """Compose on transparent RGBA, so translucent pixels never mix with a key color."""
    frame = Image.new("RGBA", (size, size))
    gauge = size - 32
    image_x = (size - gauge) // 2
    image_y = (size - 24 - gauge) // 2
    ghost = gray.resize((gauge, gauge), Image.Resampling.NEAREST)
    ghost.putalpha(ghost.getchannel("A").point(lambda alpha: round(alpha * 0.4)))
    frame.alpha_composite(ghost, (image_x, image_y))
    if usage is not None:
        fill_height = round(gauge * usage / 100)
        if fill_height > 0:
            source = color if healthy else gray
            scaled = source.resize((gauge, gauge), Image.Resampling.NEAREST)
            filled = scaled.crop((0, gauge - fill_height, gauge, gauge))
            frame.alpha_composite(filled, (image_x, image_y + gauge - fill_height))

    value_text = f"{usage:.0f}%" if usage is not None else missing_text
    label_width = round(font.getlength(value_text)) + 10
    label = Image.new("RGBA", (label_width, 24))
    ImageDraw.Draw(label).rounded_rectangle(
        (0, 0, label_width - 1, 23), radius=3, fill=(43, 32, 22, 230)
    )
    frame.alpha_composite(label, ((size - label_width) // 2, size - 24))
    ImageDraw.Draw(frame).text(
        (size // 2, size - 12), value_text, font=font, anchor="mm",
        fill="white" if healthy else "lightgray",
    )
    return frame
