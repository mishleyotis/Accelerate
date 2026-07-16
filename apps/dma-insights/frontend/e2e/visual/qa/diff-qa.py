import os, sys
from PIL import Image
PROTO, PROD, OUT = "/tmp/proto-shots", "/tmp/prod-shots", "/tmp/qa-diffs"
os.makedirs(OUT, exist_ok=True)
rows = []
for f in sorted(os.listdir(PROTO)):
    if not f.endswith(".png"): continue
    name = f.replace("proto-", "").replace(".png", "")
    pf, qf = os.path.join(PROTO, f), os.path.join(PROD, f"prod-{name}.png")
    if not os.path.exists(qf): rows.append((name, None, "missing in prod")); continue
    a, b = Image.open(pf).convert("RGB"), Image.open(qf).convert("RGB")
    w = min(a.width, b.width); h = min(a.height, b.height)
    # full-page heights differ wildly; compare the overlapping top region
    a2, b2 = a.crop((0,0,w,h)), b.crop((0,0,w,h))
    pa, pb = a2.load(), b2.load()
    diff_img = Image.new("RGB", (w,h), (255,255,255))
    pd_ = diff_img.load()
    ndiff = 0
    for y in range(0,h,2):           # sample every 2px for speed
        for x in range(0,w,2):
            ra,ga,ba = pa[x,y]; rb,gb,bb = pb[x,y]
            if abs(ra-rb)>8 or abs(ga-gb)>8 or abs(ba-bb)>8:
                ndiff += 1; pd_[x,y] = (255,0,80)
    total = (w//2)*(h//2)
    pct = 100.0*ndiff/total
    note = f"hA={a.height} hB={b.height}"
    diff_img.save(os.path.join(OUT, f"{name}-diff.png"))
    rows.append((name, pct, note))
rows.sort(key=lambda r: -(r[1] if r[1] is not None else 999))
print(f"{'pair':45s} {'diff%':>7s}  note")
for n,p,note in rows:
    print(f"{n:45s} {('%.1f'%p if p is not None else '  MISS'):>7s}  {note}")
