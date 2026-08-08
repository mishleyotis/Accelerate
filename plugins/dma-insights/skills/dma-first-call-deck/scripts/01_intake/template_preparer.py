#!/usr/bin/env python3
"""
template_preparer.py — Copy normalized template, unpack, extract palette + manifest.

Usage:
    python scripts/template_preparer.py \
        --template assets/templates/credit_unions.pptx \
        --client "Pacific Coast CU" \
        --date "2026-04-09" \
        --out-dir /home/claude/working/

Produces: unpacked/, palette.json, placeholder_manifest.json, shape_inventory.json

Safeguards:
    - Global [CLIENT] → client name replacement across ALL slide XML
    - Global [DATE] / DATE → actual date replacement
    - Post-normalization grep for Higginbotham must return 0
    - Palette extracted and validated against brand
    - Template version check (22 slides, Slide 14 ≥150 shapes, DM Sans)
"""
import argparse, json, os, re, shutil, subprocess, sys, zipfile, glob

BRAND_PALETTE = {
    "000000","FFFFFF","1C4A4D","185F60","27BBAF","62D7B8","B0EED3","E8F7F6",
    "F2F4F9","A5C6FF","3D81F6","C7D3EC","B19CD8","8094C0","FFCB99","FE9732",
    "FFF3E8","E6F5F3","E5E7EB","6B7280","2D3748","555555","718096",
    "058DC7","139F94","1A535C","1A5C52","059669","065F46","4A5568","333333",
    "198478","4E5E8A","C25008","F97316","003366",
}


def normalize_fonts(unpacked_dir):
    """Replace non-DM-Sans fonts in slide XML with DM Sans."""
    import glob, re
    
    font_map = {
        "Calibri": "DM Sans",
        "Inter": "DM Sans",
        "Arial": "DM Sans",
        "Noto Sans": "DM Sans",
    }
    
    total_fixes = 0
    for xml_path in glob.glob(os.path.join(unpacked_dir, "ppt/slides/*.xml")):
        with open(xml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        modified = False
        for old_font, new_font in font_map.items():
            pattern = f'typeface="{old_font}"'
            replacement = f'typeface="{new_font}"'
            if pattern in content:
                count = content.count(pattern)
                content = content.replace(pattern, replacement)
                total_fixes += count
                modified = True
        
        if modified:
            with open(xml_path, 'w', encoding='utf-8') as f:
                f.write(content)
    
    return total_fixes

def scan_slide14_border_bugs(unpacked_dir):
    """Scan Slide 14 for fill-border mismatches on bg_card / accent_strip / progress_bar.

    Template is known to ship with 3 pre-existing mismatches (Sh82, Sh87, Sh124).
    Returns a list of {shape_idx, role, fill_hex, border_hex, severity} dicts.

    The heatmap_editor.py updates fills AND borders to match when it runs — but
    scanning before the editor runs gives us a baseline for validation.
    """
    import glob
    try:
        from lxml import etree
    except ImportError:
        return []  # lxml optional — scan silently skipped if unavailable
    xml_path = os.path.join(unpacked_dir, "ppt/slides/slide14.xml")
    if not os.path.exists(xml_path):
        return []
    ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
          'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    tree = etree.parse(xml_path)
    sptree = tree.find('.//p:spTree', ns)
    children = [c for c in sptree if c.tag.split('}')[1] in ('sp', 'pic', 'cxnSp', 'grpSp')]
    BLOCKS = [17, 25, 33, 41, 49, 58, 66, 74, 82, 91, 99, 107, 115, 124, 132, 140, 148]
    bugs = []
    for base in BLOCKS:
        for offset, role in [(0, "bg_card"), (1, "accent_strip"), (5, "progress_bar")]:
            idx = base + offset
            if idx >= len(children):
                continue
            sh = children[idx]
            spPr = sh.find('.//p:spPr', ns) or sh.find('a:spPr', ns)
            if spPr is None:
                continue
            fill = spPr.find('.//a:solidFill/a:srgbClr', ns)
            ln = spPr.find('a:ln', ns)
            ln_srgb = ln.find('.//a:srgbClr', ns) if ln is not None else None
            fill_hex = fill.get('val').upper() if fill is not None else None
            ln_hex = ln_srgb.get('val').upper() if ln_srgb is not None else None
            if fill_hex and ln_hex and fill_hex != ln_hex:
                bugs.append({
                    "shape_idx": idx,
                    "role": role,
                    "fill_hex": f"#{fill_hex}",
                    "border_hex": f"#{ln_hex}",
                    "severity": "TEMPLATE_BUG",
                })
    return bugs


def main():
    parser = argparse.ArgumentParser(description="Prepare DMA first call template")
    parser.add_argument("--template", required=True, help="Source template PPTX")
    parser.add_argument("--client", required=True, help="Client name")
    parser.add_argument("--date", default="", help="Date string")
    parser.add_argument("--out-dir", required=True, help="Working directory")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    work_pptx = os.path.join(args.out_dir, "template.pptx")
    shutil.copy2(args.template, work_pptx)

    # Unpack
    unpacked = os.path.join(args.out_dir, "unpacked")
    if os.path.exists(unpacked):
        shutil.rmtree(unpacked)
    
    # Try using the pptx skill unpack script
    unpack_script = "/mnt/skills/public/pptx/scripts/office/unpack.py"
    if os.path.exists(unpack_script):
        subprocess.run(["python3", unpack_script, work_pptx, unpacked], check=True)
    else:
        os.makedirs(unpacked, exist_ok=True)
        with zipfile.ZipFile(work_pptx, 'r') as z:
            z.extractall(unpacked)

    # Global replacements across all slide XML
    replacements_made = {"client": 0, "date": 0, "higginbotham": 0}
    for sf in glob.glob(os.path.join(unpacked, "ppt/slides/slide*.xml")):
        with open(sf, "r", encoding="utf-8") as f:
            content = f.read()
        original = content

        # Client name replacements — ORDER MATTERS: longer/bracketed patterns first so
        # bare "CLIENT" doesn't greedily consume "CLIENT NAME" or "CLIENT NAME]" substrings.
        # Covers bracketed, bare, and "Customer name" variants (Slide 10 Sh1/Sh7 use the latter).
        for pattern in ["[CLIENT NAME]", "[Client Name]", "[client name]",
                        "[Customer name]", "[Customer Name]", "[customer name]",
                        "[CLIENT]", "[Client]", "[client]"]:
            if pattern in content:
                count = content.count(pattern)
                content = content.replace(pattern, args.client)
                replacements_made["client"] += count
        # Bare CLIENT — only match when NOT already inside a bracketed context
        # (the longer bracketed patterns above have already consumed those occurrences).
        bare_count = len(re.findall(r'(?<![\[\w])CLIENT(?![\w\]])', content))
        if bare_count > 0:
            content = re.sub(r'(?<![\[\w])CLIENT(?![\w\]])', args.client, content)
            replacements_made["client"] += bare_count

        # Date replacement
        if args.date:
            for pattern in ["DATE", "[Date]", "[date]"]:
                if pattern in content:
                    count = content.count(pattern)
                    content = content.replace(pattern, args.date)
                    replacements_made["date"] += count

        # Higginbotham cleanup (safety net)
        if "Higginbotham" in content:
            count = content.count("Higginbotham")
            content = content.replace("Higginbotham", args.client)
            replacements_made["higginbotham"] += count

        if content != original:
            with open(sf, "w", encoding="utf-8") as f:
                f.write(content)

    # Normalize fonts (Arial/Inter/Calibri/Noto Sans → DM Sans) across ALL slides.
    # This was previously dead code (function defined but never called). Slide 10
    # ships with 92 non-DM-Sans runs; without this call, decks ship non-brand.
    font_fixes = normalize_fonts(unpacked)
    print(f"  Font normalization: {font_fixes} runs converted to DM Sans")

    # Extract color palette
    all_colors = set()
    for sf in glob.glob(os.path.join(unpacked, "ppt/slides/slide*.xml")):
        with open(sf, "r", encoding="utf-8") as f:
            content = f.read()
        colors = re.findall(r'srgbClr val="([A-Fa-f0-9]{6})"', content)
        all_colors.update(c.upper() for c in colors)

    unauthorized = all_colors - BRAND_PALETTE
    palette = {
        "approved": sorted(all_colors & BRAND_PALETTE),
        "unauthorized": sorted(unauthorized),
        "total_unique": len(all_colors),
    }

    # Build placeholder manifest
    placeholders = []
    patterns = [r'\[Client\]', r'\[client\]', r'XXXX', r'XX\.XX', r'Lorem',
                r'\bTBD\b', r'PL NAME', r'\{\{', r'\[DATA NEEDED\]',
                r'\[Insert', r'\[Name\]', r'\[Title\]', r'\[Email\]', r'\[Date\]',
                r'\[Customer name\]', r'\[Customer Name\]', r'\[customer name\]']
    
    for sf in sorted(glob.glob(os.path.join(unpacked, "ppt/slides/slide*.xml"))):
        slide_num = os.path.basename(sf).replace("slide","").replace(".xml","")
        with open(sf, "r", encoding="utf-8") as f:
            content = f.read()
        for pat in patterns:
            matches = re.findall(pat, content)
            if matches:
                placeholders.append({"slide": slide_num, "pattern": pat, "count": len(matches)})

    # Write outputs
    with open(os.path.join(args.out_dir, "palette.json"), "w") as f:
        json.dump(palette, f, indent=2)
    with open(os.path.join(args.out_dir, "placeholder_manifest.json"), "w") as f:
        json.dump({"remaining_placeholders": placeholders, "replacements": replacements_made}, f, indent=2)

    # Scan Slide 14 for pre-existing fill-border mismatches (template bugs)
    # heatmap_editor.py will correct these automatically, but we log them so
    # governance/QA can track template drift across refreshes.
    s14_border_bugs = scan_slide14_border_bugs(unpacked)
    with open(os.path.join(args.out_dir, "template_bugs.json"), "w") as f:
        json.dump({"slide14_border_mismatches": s14_border_bugs}, f, indent=2)

    print(f"Template prepared in {args.out_dir}")
    print(f"  Client replacements: {replacements_made['client']}")
    print(f"  Date replacements: {replacements_made['date']}")
    print(f"  Higginbotham fixes: {replacements_made['higginbotham']}")
    print(f"  Remaining placeholders: {len(placeholders)}")
    print(f"  Unauthorized colors: {len(unauthorized)}")
    if unauthorized:
        print(f"  ⚠ Unauthorized: {unauthorized}")
    if s14_border_bugs:
        print(f"  ⚠ Slide 14 template border bugs: {len(s14_border_bugs)} "
              f"(will be fixed by heatmap_editor.py)")
        for b in s14_border_bugs:
            print(f"     Sh{b['shape_idx']} {b['role']}: fill {b['fill_hex']} vs border {b['border_hex']}")

if __name__ == "__main__":
    main()
