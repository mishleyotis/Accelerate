#!/usr/bin/env python3
"""
render_and_inspect.py — Render specific slides to PNG for VISUAL inspection by Claude.

This is the critical QA step: Claude renders the slide, VIEWs the image with its
vision capability, and judges whether text overflows, overlaps, or looks wrong.

No math. No estimation. Claude literally looks at the slide.

Usage:
    python3 scripts/04_qa/render_and_inspect.py \
        --pptx working/deck.pptx \
        --slides 6,9,13,14 \
        --outdir qa_renders/

Produces: qa_renders/slide_06.png, qa_renders/slide_09.png, etc.

Claude then calls `view qa_renders/slide_06.png` and visually checks:
  - Text clipping at shape boundaries
  - Text overlapping adjacent shapes/columns
  - Font too small to read
  - Uneven spacing or crowded layout
  - Placeholder text still visible ("[CLIENT]", "[DATA NEEDED]")

If issues found → Claude rewrites content shorter, reduces font, or adjusts.
"""
import argparse, os, subprocess, sys, glob


def render_slides(pptx_path, slide_numbers, outdir, dpi=200):
    """Convert PPTX → PDF → per-slide PNGs."""
    os.makedirs(outdir, exist_ok=True)
    
    # Step 1: PPTX → PDF via LibreOffice
    result = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", pptx_path, "--outdir", outdir],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"ERROR: LibreOffice conversion failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    
    base = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf_path = os.path.join(outdir, f"{base}.pdf")
    if not os.path.exists(pdf_path):
        # soffice sometimes names differently
        pdfs = glob.glob(os.path.join(outdir, "*.pdf"))
        if pdfs:
            pdf_path = pdfs[0]
        else:
            print("ERROR: No PDF generated", file=sys.stderr)
            sys.exit(1)
    
    # Step 2: PDF → PNGs (all pages first)
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), pdf_path, os.path.join(outdir, "all")],
        capture_output=True, timeout=120
    )
    
    # Step 3: Rename requested slides to clean names
    all_pngs = sorted(glob.glob(os.path.join(outdir, "all-*.png")))
    output_files = []
    
    for slide_num in slide_numbers:
        idx = slide_num - 1  # 0-based
        if idx < len(all_pngs):
            clean_name = os.path.join(outdir, f"slide_{slide_num:02d}.png")
            os.rename(all_pngs[idx], clean_name)
            output_files.append(clean_name)
            print(f"  ✓ Slide {slide_num} → {clean_name}")
        else:
            print(f"  ⚠ Slide {slide_num} not found (deck has {len(all_pngs)} slides)")
    
    # Cleanup temp files
    for f in glob.glob(os.path.join(outdir, "all-*.png")):
        os.remove(f)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    
    return output_files


def main():
    parser = argparse.ArgumentParser(
        description="Render PPTX slides to PNG for Claude's visual inspection"
    )
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--slides", required=True, 
                       help="Comma-separated slide numbers (e.g., 1,6,9,13,14)")
    parser.add_argument("--outdir", default="qa_renders")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()
    
    slide_numbers = [int(s.strip()) for s in args.slides.split(",")]
    
    files = render_slides(args.pptx, slide_numbers, args.outdir, args.dpi)
    
    print(f"\n{'='*50}")
    print(f"RENDERED {len(files)} slides for visual inspection.")
    print(f"{'='*50}")
    print(f"\nNEXT STEP: Claude must VIEW each image and check for:")
    print(f"  1. Text overflowing shape boundaries")
    print(f"  2. Text overlapping adjacent shapes/columns")
    print(f"  3. Font too small to read at presentation size")
    print(f"  4. Uneven spacing or crowded sections")
    print(f"  5. Placeholder text still visible")
    print(f"\nFiles to view:")
    for f in files:
        print(f"  view {f}")


if __name__ == "__main__":
    main()
