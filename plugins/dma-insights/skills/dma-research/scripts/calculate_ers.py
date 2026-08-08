#!/usr/bin/env python3
"""
Calculate Evidence Rank Scores (ERS) for all evidence items.

Usage:
    python calculate_ers.py <evidence_index.json> [--update] [--report]

Computes: ERS = 0.35×Tier + 0.25×Recency + 0.20×Specificity + 0.20×Corroboration
If --update: writes ERS scores back into the evidence index JSON.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta


# Tier scores
TIER_SCORES = {'T1': 5.0, 'T2': 4.0, 'T3': 3.0, 'T4': 2.0, 'T5': 1.0}

# Recency scores
def recency_score(date_str, recency_tag=''):
    """Calculate recency score from date or tag."""
    if recency_tag:
        tag_scores = {'CURRENT': 5.0, 'RECENT': 4.0, 'DATED': 3.0, 'STALE': 2.0,
                      'LEGACY': 1.5, 'ARCHIVAL': 1.0, 'UNVERIFIED': 2.0}
        return tag_scores.get(recency_tag.upper(), 2.0)
    
    if not date_str:
        return 2.0  # unknown date
    
    try:
        pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        now = datetime.now(pub_date.tzinfo) if pub_date.tzinfo else datetime.now()
        age_months = (now - pub_date).days / 30
        
        if age_months <= 12:
            return 5.0
        elif age_months <= 24:
            return 4.0
        elif age_months <= 36:
            return 3.0
        elif age_months <= 48:
            return 2.0
        else:
            return 1.0
    except (ValueError, TypeError):
        return 2.0


def calculate_ers(item, all_items=None):
    """Calculate ERS for a single evidence item."""
    tier = item.get('tier', 'T5')
    tier_s = TIER_SCORES.get(tier, 1.0)
    
    recency_s = recency_score(
        item.get('date_published', ''),
        item.get('recency_tag', '')
    )
    
    # Specificity: use the average of fact-level specificity scores, or item-level
    facts = item.get('facts', [])
    if facts:
        spec_scores = [f.get('specificity_score', 2.0) for f in facts]
        specificity_s = sum(spec_scores) / len(spec_scores)
    else:
        specificity_s = item.get('ers_scores', {}).get('specificity_score', 2.0)
    
    # Corroboration: check how many other items corroborate this one
    corr_ids = item.get('corroborating_evidence_ids', [])
    if len(corr_ids) >= 3:
        corroboration_s = 5.0
    elif len(corr_ids) >= 2:
        corroboration_s = 4.0
    elif len(corr_ids) >= 1:
        if tier in ('T1', 'T2'):
            corroboration_s = 3.5
        else:
            corroboration_s = 3.0
    else:
        # Single source — score based on tier
        if tier in ('T1', 'T2'):
            corroboration_s = 3.0
        elif tier == 'T3':
            corroboration_s = 2.0
        else:
            corroboration_s = 1.0
    
    ers = (0.35 * tier_s) + (0.25 * recency_s) + (0.20 * specificity_s) + (0.20 * corroboration_s)
    
    return {
        'tier_score': round(tier_s, 2),
        'recency_score': round(recency_s, 2),
        'specificity_score': round(specificity_s, 2),
        'corroboration_score': round(corroboration_s, 2),
        'ers_total': round(ers, 2),
    }


def main():
    parser = argparse.ArgumentParser(description='Calculate ERS for evidence items')
    parser.add_argument('evidence_index', help='Path to evidence_index.json')
    parser.add_argument('--update', action='store_true', help='Write ERS back to JSON')
    parser.add_argument('--report', action='store_true', help='Print detailed report')
    args = parser.parse_args()
    
    with open(args.evidence_index) as f:
        data = json.load(f)
    
    items = data.get('evidence_items', [])
    
    if not items:
        print("No evidence items found.")
        sys.exit(0)
    
    # Calculate ERS for all items
    ers_values = []
    for item in items:
        ers = calculate_ers(item, items)
        item['ers_scores'] = ers
        ers_values.append(ers['ers_total'])
    
    # Summary
    print(f"\n{'='*50}")
    print(f"ERS CALCULATION COMPLETE")
    print(f"{'='*50}")
    print(f"Items scored:    {len(items)}")
    print(f"Average ERS:     {sum(ers_values)/len(ers_values):.2f}")
    print(f"Highest ERS:     {max(ers_values):.2f}")
    print(f"Lowest ERS:      {min(ers_values):.2f}")
    print(f"High (≥3.5):     {sum(1 for v in ers_values if v >= 3.5)}")
    print(f"Medium (2.5-3.5): {sum(1 for v in ers_values if 2.5 <= v < 3.5)}")
    print(f"Low (<2.5):      {sum(1 for v in ers_values if v < 2.5)}")
    
    if args.report:
        print(f"\n--- TOP 10 HIGHEST ERS ---")
        sorted_items = sorted(items, key=lambda x: x['ers_scores']['ers_total'], reverse=True)
        for item in sorted_items[:10]:
            ers = item['ers_scores']
            print(f"  {item['evidence_id']} ({item.get('tier','?')}, ERS={ers['ers_total']:.2f}): "
                  f"{item.get('source_name', '?')[:50]}")
        
        print(f"\n--- BOTTOM 10 LOWEST ERS ---")
        for item in sorted_items[-10:]:
            ers = item['ers_scores']
            print(f"  {item['evidence_id']} ({item.get('tier','?')}, ERS={ers['ers_total']:.2f}): "
                  f"{item.get('source_name', '?')[:50]}")
    
    if args.update:
        with open(args.evidence_index, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nUpdated: {args.evidence_index}")


if __name__ == '__main__':
    main()
