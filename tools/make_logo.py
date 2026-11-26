"""Draw an original logo inspired by SchoolHub's navy and cyan palette."""
from PIL import Image, ImageDraw
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "assets"
out.mkdir(exist_ok=True)
s = 1024
image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
d = ImageDraw.Draw(image)
d.rounded_rectangle((40, 40, 984, 984), radius=220, fill="#0a1120", outline="#3788ff", width=22)
d.rounded_rectangle((88, 88, 936, 936), radius=180, outline="#314965", width=8)
# Open book and central hub; bold, legible at small Windows icon sizes.
d.polygon([(200, 300), (430, 340), (512, 408), (594, 340), (824, 300),
           (824, 670), (594, 710), (512, 776), (430, 710), (200, 670)], fill="#76daff")
d.polygon([(240, 365), (422, 397), (488, 450), (488, 700), (425, 665), (240, 635)], fill="#1b2b43")
d.polygon([(784, 365), (602, 397), (536, 450), (536, 700), (599, 665), (784, 635)], fill="#1b2b43")
for x1, x2 in ((284, 424), (600, 740)):
    for y in (470, 550):
        d.rounded_rectangle((x1, y, x2, y + 22), radius=11, fill="#eff6ff")
d.ellipse((439, 150, 585, 296), fill="#42dfaa", outline="#0a1120", width=12)
d.line((482, 222, 503, 245, 548, 198), fill="#0a1120", width=16, joint="curve")
image.resize((512,512), Image.Resampling.LANCZOS).save(out / "schoolhub_icon.png")
image.save(out / "schoolhub.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
