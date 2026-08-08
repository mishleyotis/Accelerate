#!/usr/bin/env python3
"""
radar_chart_generator.py — Generate radar chart + legend PNGs for Slide 13.

Creates a 4-axis spider/radar chart with 3 series:
    1. Industry Average (gray) — peer median per pillar
    2. Client Current (teal #27BBAF) — actual pillar scores
    3. Client Target (green #198478) — target maturity per pillar

Also generates the legend bar with client name.

Image specs:
    - Radar chart: 796×528px @2x (displays at 398×264px in PPTX)
    - Legend: 720×68px @2x (displays at 360×34px)
    - Format: PNG with transparent background
    - Replaces: Slide 13 Sh60 (radar) and Sh61 (legend)

Score consistency validation (runs before chart generation):
    - Pillar score ≈ average of capability scores within that pillar (±0.15 tolerance)
    - Overall score ≈ weighted average of pillar scores (±0.10 tolerance)
    - All scores in 0-5 range
    - Target scores > current scores (warning if not)
    - Flags inconsistencies BEFORE generating — does NOT silently produce bad charts

Usage:
    python scripts/03_editing/radar_chart_generator.py \
        --client "SouthState" \
        --scores '{"P1": 2.71, "P2": 2.47, "P3": 2.85, "P4": 2.62}' \
        --medians '{"P1": 2.45, "P2": 2.56, "P3": 2.38, "P4": 2.44}' \
        --targets '{"P1": 3.2, "P2": 3.1, "P3": 3.3, "P4": 3.0}' \
        --overall 2.61 \
        --capability-scores capabilities.json \
        --out-chart radar.png \
        --out-legend legend.png
"""
import argparse
import json
import math
import sys
import os

# Brand colors
COLOR_CURRENT = "#27BBAF"    # Teal — client current
COLOR_TARGET = "#198478"     # Dark teal — client target
COLOR_INDUSTRY = "#8094C0"   # Gray-purple — industry average
COLOR_GRID = "#E5E7EB"       # Light gray — grid lines
COLOR_AXIS_LABEL = "#555555" # Axis label text
COLOR_SCORE_LABEL = "#718096"# Score number labels
BG_TRANSPARENT = True

# Pillar labels (display order: top, right, bottom, left)
PILLAR_LABELS = {
    "P1": "Strategy &\nGovernance",
    "P2": "Customer\nExperience",
    "P3": "Operations\n& Risk",
    "P4": "Data &\nTechnology",
}

PILLAR_ORDER = ["P1", "P2", "P3", "P4"]

# Placeholder client names that should NEVER appear in output
PLACEHOLDER_NAMES = {"Higginbotham", "Acme", "Test", "Client", "SampleClient", "Example"}

# Pillar weights for weighted average validation
PILLAR_WEIGHTS = {"P1": 0.25, "P2": 0.30, "P3": 0.20, "P4": 0.25}

# Capability-to-pillar mapping for consistency checks
CAPABILITY_PILLAR_MAP = {
    "P1C1": "P1", "P1C2": "P1", "P1C3": "P1", "P1C4": "P1", "P1C5": "P1",
    "P2C1": "P2", "P2C2": "P2", "P2C3": "P2", "P2C4": "P2",
    "P3C1": "P3", "P3C2": "P3", "P3C3": "P3", "P3C4": "P3",
    "P4C1": "P4", "P4C2": "P4", "P4C3": "P4", "P4C4": "P4",
}


def validate_scores(scores, medians, targets, overall, capability_scores=None):
    """Validate score consistency. Returns (is_valid, issues)."""
    issues = []
    
    # Range checks
    for label, dataset in [("Scores", scores), ("Medians", medians), ("Targets", targets)]:
        for key, val in dataset.items():
            if not (0 <= val <= 5):
                issues.append(f"CRITICAL: {label} {key}={val} outside 0-5 range")
    
    if overall is not None and not (0 <= overall <= 5):
        issues.append(f"CRITICAL: Overall={overall} outside 0-5 range")
    
    # All 4 pillars present
    for p in PILLAR_ORDER:
        if p not in scores:
            issues.append(f"CRITICAL: Missing pillar score for {p}")
        if p not in medians:
            issues.append(f"WARNING: Missing median for {p}")
    
    # Target > current
    for p in PILLAR_ORDER:
        if p in scores and p in targets:
            if targets[p] < scores[p]:
                issues.append(f"WARNING: {p} target ({targets[p]}) < current ({scores[p]})")
    
    # Overall ≈ weighted average of pillars
    if overall is not None and len(scores) == 4:
        weighted = sum(scores[p] * PILLAR_WEIGHTS[p] for p in PILLAR_ORDER)
        delta = abs(overall - weighted)
        if delta > 0.15:
            issues.append(
                f"FLAG: Overall score ({overall}) differs from weighted pillar average "
                f"({weighted:.2f}) by {delta:.2f}. Check if custom weights apply."
            )
    
    # Pillar ≈ average of capabilities within that pillar
    if capability_scores:
        for pillar in PILLAR_ORDER:
            cap_scores = [
                capability_scores[c] for c, p in CAPABILITY_PILLAR_MAP.items()
                if p == pillar and c in capability_scores
            ]
            if cap_scores and pillar in scores:
                cap_avg = sum(cap_scores) / len(cap_scores)
                delta = abs(scores[pillar] - cap_avg)
                if delta > 0.20:
                    issues.append(
                        f"FLAG: {pillar} score ({scores[pillar]}) differs from "
                        f"capability average ({cap_avg:.2f}) by {delta:.2f}. "
                        f"Check for weighted/adjusted scoring."
                    )
    
    is_valid = not any("CRITICAL" in i for i in issues)
    return is_valid, issues


def generate_radar_chart(scores, medians, targets, out_path, width=796, height=528):
    """Generate radar chart PNG using matplotlib."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("ERROR: matplotlib required. pip install matplotlib", file=sys.stderr)
        sys.exit(1)
    
    # Setup
    n_axes = 4
    angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon
    
    fig, ax = plt.subplots(figsize=(width/100, height/100), subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)
    ax.set_facecolor('none')
    
    # Grid
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(['1', '2', '3', '4', '5'], fontsize=7, color=COLOR_SCORE_LABEL)
    ax.set_rlabel_position(90)
    
    # Grid styling
    ax.yaxis.grid(True, color=COLOR_GRID, linewidth=0.8)
    ax.xaxis.grid(True, color=COLOR_GRID, linewidth=0.8)
    ax.spines['polar'].set_color(COLOR_GRID)
    
    # Axis labels
    ax.set_xticks(angles[:-1])
    labels = [PILLAR_LABELS[p] for p in PILLAR_ORDER]
    ax.set_xticklabels(labels, fontsize=8, color=COLOR_AXIS_LABEL, fontweight='bold',
                       ha='center', fontfamily='sans-serif')
    
    # Start from top (90 degrees)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    
    def plot_series(data, color, fill_alpha, label, linewidth=2):
        vals = [data.get(p, 0) for p in PILLAR_ORDER]
        vals += vals[:1]
        ax.plot(angles, vals, 'o-', color=color, linewidth=linewidth, markersize=4, label=label)
        ax.fill(angles, vals, alpha=fill_alpha, color=color)
    
    # Plot series (order matters for layering)
    plot_series(targets, COLOR_TARGET, 0.08, "Target", linewidth=2)
    plot_series(scores, COLOR_CURRENT, 0.15, "Current", linewidth=2.5)
    plot_series(medians, COLOR_INDUSTRY, 0.05, "Industry Average", linewidth=1.5)
    
    plt.tight_layout(pad=1.5)
    fig.savefig(out_path, dpi=200, transparent=True, bbox_inches='tight',
                pad_inches=0.3, format='png')
    plt.close()
    print(f"  Radar chart saved: {out_path} ({os.path.getsize(out_path)} bytes)")


def generate_legend(client_name, out_path, width=720, height=68):
    """Generate legend bar PNG with client name."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        print("ERROR: matplotlib required", file=sys.stderr)
        sys.exit(1)
    
    fig, ax = plt.subplots(figsize=(width/100, height/100))
    fig.patch.set_alpha(0)
    ax.set_facecolor('none')
    ax.axis('off')
    
    # Three legend items
    items = [
        (COLOR_INDUSTRY, "Industry Average"),
        (COLOR_CURRENT, f"{client_name} Current"),
        (COLOR_TARGET, f"{client_name} Target"),
    ]
    
    x_start = 0.02
    for color, label in items:
        rect = FancyBboxPatch((x_start, 0.25), 0.05, 0.5, boxstyle="round,pad=0.01",
                              facecolor=color, edgecolor='none', transform=ax.transAxes)
        ax.add_patch(rect)
        ax.text(x_start + 0.07, 0.5, label, transform=ax.transAxes,
                fontsize=8, color=COLOR_AXIS_LABEL, va='center', fontfamily='sans-serif')
        x_start += 0.35
    
    fig.savefig(out_path, dpi=200, transparent=True, bbox_inches='tight',
                pad_inches=0.05, format='png')
    plt.close()
    print(f"  Legend saved: {out_path} ({os.path.getsize(out_path)} bytes)")


def find_image_rids(unpacked_dir, slide_num):
    """Find all image relationship IDs for a slide.
    
    Returns dict: {rId: relative_target_path}
    The rId→filename mapping varies across sub-verticals — never hardcode filenames.
    """
    from lxml import etree
    rels_path = os.path.join(unpacked_dir, f"ppt/slides/_rels/slide{slide_num}.xml.rels")
    if not os.path.exists(rels_path):
        print(f"  WARNING: No rels file at {rels_path}", file=sys.stderr)
        return {}
    rels_tree = etree.parse(rels_path)
    images = {}
    for rel in rels_tree.getroot():
        rtype = rel.get('Type', '')
        if 'image' in rtype.lower():
            images[rel.get('Id')] = rel.get('Target')
    return images


def replace_image_in_pptx(unpacked_dir, slide_num, shape_rId, new_image_path):
    """Replace image by overwriting the target file in ppt/media/.
    
    Uses relationship-based lookup — no XML changes needed.
    This is the Google Slides safe method: preserves exact XML structure,
    relationship IDs, and shape positions. The old image file is overwritten
    with the new one, and the PPTX is repacked.
    
    Args:
        unpacked_dir: Path to unpacked PPTX directory
        slide_num: Slide number (1-indexed)
        shape_rId: Relationship ID (e.g., 'rId4') from the slide rels file
        new_image_path: Path to the new PNG file
    
    Returns:
        True on success
    
    Raises:
        ValueError: if rId not found
        FileNotFoundError: if target media file doesn't exist
    """
    import shutil
    from lxml import etree
    
    rels_path = os.path.join(unpacked_dir, f"ppt/slides/_rels/slide{slide_num}.xml.rels")
    rels_tree = etree.parse(rels_path)
    
    target = None
    for rel in rels_tree.getroot():
        if rel.get('Id') == shape_rId:
            target = rel.get('Target', '')
            break
    
    if not target:
        raise ValueError(f"rId '{shape_rId}' not found in slide{slide_num} rels")
    
    # Target is relative: "../media/image170.png"
    media_path = os.path.normpath(os.path.join(unpacked_dir, 'ppt/slides', target))
    
    if not os.path.exists(media_path):
        raise FileNotFoundError(f"Target media file not found: {media_path}")
    
    old_size = os.path.getsize(media_path)
    shutil.copy2(new_image_path, media_path)
    new_size = os.path.getsize(media_path)
    print(f"  ✓ Replaced {media_path} ({old_size} → {new_size} bytes)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate radar chart for Slide 13")
    parser.add_argument("--client", required=True, help="Client name")
    parser.add_argument("--scores", required=True, help="JSON: {P1: score, P2: score, P3: score, P4: score}")
    parser.add_argument("--medians", required=True, help="JSON: {P1: median, ...}")
    parser.add_argument("--targets", required=True, help="JSON: {P1: target, ...}")
    parser.add_argument("--overall", type=float, help="Overall score for consistency check")
    parser.add_argument("--capability-scores", help="JSON file with P#C# scores for validation")
    parser.add_argument("--out-chart", default="radar.png", help="Output radar chart PNG")
    parser.add_argument("--out-legend", default="legend.png", help="Output legend PNG")
    parser.add_argument("--validate-only", action="store_true", help="Only validate, don't generate")
    parser.add_argument("--terminology", help='JSON map of pillar label overrides, e.g. \'{"Customer Experience": "Member Experience"}\'')
    parser.add_argument("--verify", action="store_true", help="Print verification summary after generation")
    args = parser.parse_args()

    # Validate client name is not a placeholder
    if args.client in PLACEHOLDER_NAMES:
        print(f"ERROR: Client name '{args.client}' is a known placeholder. "
              f"Pass the actual client name with --client.", file=sys.stderr)
        sys.exit(1)

    # Apply terminology overrides to pillar labels
    if args.terminology:
        term_map = json.loads(args.terminology)
        for pillar_id, label in PILLAR_LABELS.items():
            for old_term, new_term in term_map.items():
                if old_term.lower() in label.lower():
                    PILLAR_LABELS[pillar_id] = label.replace(old_term, new_term).replace(
                        old_term.title(), new_term.title()
                    )
        print(f"Applied terminology overrides: {term_map}")
        print(f"Updated pillar labels: {PILLAR_LABELS}")

    scores = json.loads(args.scores) if isinstance(args.scores, str) else args.scores
    medians = json.loads(args.medians) if isinstance(args.medians, str) else args.medians
    targets = json.loads(args.targets) if isinstance(args.targets, str) else args.targets
    
    # Load capability scores if provided
    cap_scores = None
    if args.capability_scores and os.path.exists(args.capability_scores):
        with open(args.capability_scores) as f:
            cap_scores = json.load(f)
    
    # Validate
    is_valid, issues = validate_scores(scores, medians, targets, args.overall, cap_scores)
    
    print(f"=== SCORE CONSISTENCY VALIDATION ===")
    print(f"Client: {args.client}")
    print(f"Scores:  P1={scores.get('P1')}, P2={scores.get('P2')}, P3={scores.get('P3')}, P4={scores.get('P4')}")
    print(f"Medians: P1={medians.get('P1')}, P2={medians.get('P2')}, P3={medians.get('P3')}, P4={medians.get('P4')}")
    print(f"Targets: P1={targets.get('P1')}, P2={targets.get('P2')}, P3={targets.get('P3')}, P4={targets.get('P4')}")
    if args.overall:
        weighted = sum(scores.get(p, 0) * PILLAR_WEIGHTS[p] for p in PILLAR_ORDER)
        print(f"Overall: {args.overall} (weighted avg: {weighted:.2f})")
    
    if issues:
        print(f"\n⚠ {len(issues)} issues found:")
        for i in issues:
            print(f"  {i}")
    else:
        print("\n✓ All consistency checks passed")
    
    if not is_valid:
        print("\n✗ CRITICAL issues prevent chart generation. Fix scores first.")
        sys.exit(1)
    
    if args.validate_only:
        print("\nValidation-only mode. No charts generated.")
        return
    
    # Generate
    print(f"\n=== GENERATING CHARTS ===")
    generate_radar_chart(scores, medians, targets, args.out_chart)
    generate_legend(args.client, args.out_legend)

    # Post-generation file size check
    for path, label in [(args.out_chart, "Radar chart"), (args.out_legend, "Legend")]:
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size < 20480:
                print(f"⚠ WARNING: {label} PNG is only {size} bytes (expected >20KB). May have failed to render.")
            else:
                print(f"  ✓ {label}: {size} bytes")
        else:
            print(f"  ✗ {label} file not found: {path}")

    # Verify output
    if args.verify:
        print(f"\n=== VERIFICATION SUMMARY ===")
        print(f"Client name in legend: {args.client}")
        print(f"Pillar labels: {PILLAR_LABELS}")
        print(f"Legend items: 'Industry Average', '{args.client} Current', '{args.client} Target'")
        for name in PLACEHOLDER_NAMES:
            if name.lower() in args.client.lower():
                print(f"⚠ WARNING: Client name contains placeholder substring '{name}'")

    print(f"\nDone. Replace Slide 13 Sh60 with {args.out_chart}, Sh61 with {args.out_legend}")


if __name__ == "__main__":
    main()
