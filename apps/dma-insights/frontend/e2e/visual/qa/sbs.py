import sys, os
from PIL import Image, ImageDraw
name = sys.argv[1]; crop_h = int(sys.argv[2]) if len(sys.argv)>2 else 2200
a = Image.open(f"/tmp/proto-shots/proto-{name}.png").convert("RGB")
b = Image.open(f"/tmp/prod-shots/prod-{name}.png").convert("RGB")
h = min(max(a.height,b.height), crop_h)
def fit(img):
    c = img.crop((0,0,img.width,min(img.height,h)))
    scale = 840/c.width
    return c.resize((840, int(c.height*scale)))
fa, fb = fit(a), fit(b)
H = max(fa.height, fb.height)+30
canvas = Image.new("RGB",(1700,H),(24,24,24))
canvas.paste(fa,(0,30)); canvas.paste(fb,(860,30))
d = ImageDraw.Draw(canvas)
d.text((10,8),f"PROTOTYPE · {name}",fill=(120,255,200)); d.text((870,8),f"PRODUCTION · {name}",fill=(255,160,120))
canvas.save(f"/tmp/qa-sbs/{name}.png")
print("ok", name, canvas.size)
