from pathlib import Path
import unittest

from PIL import Image, ImageFont, ImageOps

from rendering import render_frame


class TransparencyTests(unittest.TestCase):
    def test_ghost_keeps_gray_rgb_and_partial_alpha_until_windows_composites(self):
        font = ImageFont.load_default()
        assets = Path(__file__).resolve().parents[1] / "assets"
        for style in ("round", "antlers"):
            with Image.open(assets / f"deer-{style}.png") as image:
                color = image.convert("RGBA")
            gray = ImageOps.grayscale(color).convert("RGBA")
            gray.putalpha(color.getchannel("A"))
            for size in (128, 160):
                with self.subTest(style=style, size=size):
                    frame = render_frame(color, gray, size, 42, True, font)
                    scale = (size - 32) // 16
                    ghost_samples = 0
                    fill_samples = 0
                    for y in range(16):
                        for x in range(16):
                            if color.getpixel((x, y))[3] != 255:
                                continue
                            point = (16 + x * scale + scale // 2,
                                     4 + y * scale + scale // 2)
                            if y < 8:
                                r, g, b, alpha = frame.getpixel(point)
                                self.assertEqual((r, g, b), gray.getpixel((x, y))[:3])
                                self.assertEqual(alpha, 102)
                                ghost_samples += 1
                            elif y > 10:
                                self.assertEqual(frame.getpixel(point), color.getpixel((x, y)))
                                fill_samples += 1
                    self.assertGreater(ghost_samples, 0)
                    self.assertGreater(fill_samples, 0)
                    self.assertEqual(frame.getpixel((0, 0))[3], 0)

    def test_last_usage_remains_filled_in_gray_after_an_error(self):
        color = Image.new("RGBA", (16, 16), (183, 123, 67, 255))
        gray = ImageOps.grayscale(color).convert("RGBA")
        frame = render_frame(color, gray, 128, 42, False, ImageFont.load_default())
        self.assertEqual(frame.getpixel((20, 90)), gray.getpixel((0, 0)))


if __name__ == "__main__":
    unittest.main()
