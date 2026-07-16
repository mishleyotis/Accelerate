"""Contact sheets: one per page-type, ALL entities tiled (4 cols)."""
import os, sys
from PIL import Image, ImageDraw

ROOT = "/tmp/corpus_shots"
OUT = "/tmp/deliverable/contact-sheets"
os.makedirs(OUT, exist_ok=True)
PAGES = ["overview","insights","heatmap","platform","context","health","techstack","runs"]
entities = sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT,d)) and d != "_global")
COLS, TW = 4, 420
for page in PAGES:
    tiles = []
    for e in entities:
        p = os.path.join(ROOT, e, f"{page}.png")
        if os.path.exists(p):
            try:
                img = Image.open(p).convert("RGB")
                th = int(img.height * TW / img.width)
                tiles.append((e, img.resize((TW, min(th, 360)))))
            except Exception:
                pass
    if not tiles: continue
    rows = (len(tiles)+COLS-1)//COLS
    CH = 360+34
    sheet = Image.new("RGB",(COLS*(TW+12)+12, rows*CH+50),(18,18,18))
    d = ImageDraw.Draw(sheet)
    d.text((14,12), f"DMA Insights · {page.upper()} · {len(tiles)} clients · 2026-06-11", fill=(120,255,200))
    for i,(name,img) in enumerate(tiles):
        x = 12+(i%COLS)*(TW+12); y = 44+(i//COLS)*CH
        sheet.paste(img.crop((0,0,TW,min(img.height,360))),(x,y+22))
        d.text((x,y+4), name[:52], fill=(230,230,230))
    sheet.save(os.path.join(OUT, f"{page}-all-clients.png"), optimize=True)
    print(f"{page}: {len(tiles)} tiles")
print("done")
