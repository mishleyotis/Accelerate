#!/usr/bin/env python3
"""
Merge evidence from multiple batch checkpoints into a single evidence index.

Usage:
    python merge_evidence.py <checkpoint_dir> [--output <merged_index.json>]
    python merge_evidence.py /home/claude/dma_checkpoints/ --output merged_evidence.json

Merges all evidence_index checkpoint files from Batches 1-3 into a single
consolidated index. Handles:
  - Deduplication (same source found in multiple batches)
  - Corroboration linking (identifies cross-references)
  - ERS recalculation (corroboration scores update when new links found)
  - Subcap mapping merge (combines mappings from different batches)
  - Conflict detection (flags contradictory evidence pairs)
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime


def load_checkpoint_files(checkpoint_dir):
    """Load all evidence index checkpoint files."""
    evidence_files = []
    for f in sorted(os.listdir(checkpoint_dir)):
        if f.endswith('_evidence_index.json') or f == '01_evidence_index.json':
            filepath = os.path.join(checkpoint_dir, f)
            with open(filepath, 'r') as fh:
                data = json.load(fh)
                evidence_files.append({
                    'filename': f,
                    'data': data,
                    'batch': data.get('metadata', {}).get('batches_completed', [])
                })
    return evidence_files


def deduplicate_evidence(all_items):
    """Deduplicate evidence items by source URL and source name."""
    seen = {}
    duplicates = []
    unique = []

    for item in all_items:
        key = (item.get('source_url', ''), item.get('source_name', ''))
        if key in seen:
            # Merge facts from duplicate into original
            original = seen[key]
            existing_fact_ids = {f['fact_id'] for f in original.get('facts', [])}
            for fact in item.get('facts', []):
                if fact['fact_id'] not in existing_fact_ids:
                    original['facts'].append(fact)
                    existing_fact_ids.add(fact['fact_id'])

            # Merge subcap mappings
            existing_mappings = set()
            for f in original.get('facts', []):
                existing_mappings.update(f.get('subcap_mappings', []))
            for f in item.get('facts', []):
                existing_mappings.update(f.get('subcap_mappings', []))

            duplicates.append({
                'duplicate_id': item['evidence_id'],
                'merged_into': original['evidence_id'],
                'additional_facts': len(item.get('facts', []))
            })
        else:
            seen[key] = item
            unique.append(item)

    return unique, duplicates


def build_subcap_evidence_map(evidence_items):
    """Build a map of subcap_id → list of evidence items that map to it."""
    subcap_map = defaultdict(list)
    for item in evidence_items:
        for fact in item.get('facts', []):
            for subcap_id in fact.get('subcap_mappings', []):
                subcap_map[subcap_id].append({
                    'evidence_id': item['evidence_id'],
                    'fact_id': fact['fact_id'],
                    'tier': item['tier'],
                    'ers_total': item.get('ers_scores', {}).get('ers_total', 0),
                    'claim_type': fact.get('claim_type', 'UNKNOWN'),
                    'supports_or_challenges': fact.get('supports_or_challenges', 'supports')
                })
    return dict(subcap_map)


def identify_corroboration(evidence_items):
    """Identify pairs of evidence items that corroborate or contradict each other."""
    # Group by subcap mapping
    subcap_map = defaultdict(list)
    for item in evidence_items:
        for fact in item.get('facts', []):
            for subcap_id in fact.get('subcap_mappings', []):
                subcap_map[subcap_id].append({
                    'evidence_id': item['evidence_id'],
                    'fact_id': fact['fact_id'],
                    'source_url': item.get('source_url', ''),
                    'source_name': item.get('source_name', ''),
                    'supports_or_challenges': fact.get('supports_or_challenges', 'supports')
                })

    corroboration_pairs = []
    contradiction_pairs = []

    for subcap_id, items in subcap_map.items():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                # Skip same-source pairs
                if a['source_url'] == b['source_url'] and a['source_url']:
                    continue
                if a['supports_or_challenges'] == b['supports_or_challenges']:
                    corroboration_pairs.append({
                        'subcap_id': subcap_id,
                        'evidence_a': a['evidence_id'],
                        'evidence_b': b['evidence_id'],
                        'type': 'corroboration'
                    })
                else:
                    contradiction_pairs.append({
                        'subcap_id': subcap_id,
                        'evidence_a': a['evidence_id'],
                        'evidence_b': b['evidence_id'],
                        'type': 'contradiction'
                    })

    return corroboration_pairs, contradiction_pairs


def recalculate_ers(evidence_items, corroboration_pairs):
    """Recalculate ERS scores with updated corroboration counts."""
    # Count corroborations per evidence item
    corr_count = defaultdict(set)
    for pair in corroboration_pairs:
        corr_count[pair['evidence_a']].add(pair['evidence_b'])
        corr_count[pair['evidence_b']].add(pair['evidence_a'])

    TIER_SCORES = {'T1': 5.0, 'T2': 4.0, 'T3': 3.0, 'T4': 2.0, 'T5': 1.0}
    RECENCY_MAP = {'CURRENT': 5.0, 'RECENT': 4.0, 'DATED': 3.0, 'STALE': 2.0, 'ARCHIVAL': 1.0}

    for item in evidence_items:
        ers = item.get('ers_scores', {})
        tier_score = TIER_SCORES.get(item.get('tier', 'T5'), 1.0)
        recency_score = RECENCY_MAP.get(item.get('recency_tag', 'ARCHIVAL'), 1.0)
        specificity_score = ers.get('specificity_score', 2.0)

        # Update corroboration score
        n_corr = len(corr_count.get(item['evidence_id'], set()))
        if n_corr >= 3:
            corr_score = 5.0
        elif n_corr == 2:
            corr_score = 4.0
        elif n_corr == 0:
            # Single source — score based on tier
            corr_score = 3.0 if item.get('tier') in ('T1', 'T2') else (
                2.0 if item.get('tier') == 'T3' else 1.0)
        else:
            corr_score = 4.0

        ers_total = (0.35 * tier_score + 0.25 * recency_score +
                     0.20 * specificity_score + 0.20 * corr_score)

        item['ers_scores'] = {
            'tier_score': tier_score,
            'recency_score': recency_score,
            'specificity_score': specificity_score,
            'corroboration_score': corr_score,
            'ers_total': round(ers_total, 2)
        }
        item['corroborating_evidence_ids'] = list(corr_count.get(item['evidence_id'], set()))

    return evidence_items


def calculate_coverage_stats(subcap_map, total_subcaps=None):
    """Evidence coverage against THIS RUN'S engagement set.

    AUD-0051: `total_subcaps=836` was baked into the signature, so coverage
    was computed against a taxonomy that no longer exists — a complete v7.0
    run reported 101.8% coverage and a NEGATIVE `no_evidence` count, both of
    which read as data. The denominator is now required, because the honest
    one is the SELECTED set: a focused engagement of 200 cells is not 23%
    covered, it is fully covered at its own scope, and the catalogue's 851 is
    the wrong denominator for it too.

    `total_subcaps` is None-safe on purpose: an unknown denominator yields a
    null percentage, never a plausible one (invariant 9)."""
    ready = sum(1 for v in subcap_map.values() if len(v) >= 3)
    thin = sum(1 for v in subcap_map.values() if 1 <= len(v) < 3)
    have = len(subcap_map)
    if total_subcaps is None:
        return {
            'total_subcaps': None,
            'with_evidence': have,
            'ready_3plus': ready,
            'thin_1_2': thin,
            'no_evidence': None,
            'coverage_pct': None,
            'basis': ('no engagement set supplied, so coverage has no '
                      'denominator. Pass the count of SELECTED subcaps — the '
                      'workbook seeds one row per selection and '
                      'Run_Metadata.subcaps_selected records it.'),
        }
    if have > total_subcaps:
        raise ValueError(
            f"{have} subcaps carry evidence against an engagement set of "
            f"{total_subcaps}. Coverage above 100% and a negative gap are the "
            f"AUD-0051 signature: the denominator is not this run's.")
    return {
        'total_subcaps': total_subcaps,
        'with_evidence': have,
        'ready_3plus': ready,
        'thin_1_2': thin,
        'no_evidence': total_subcaps - have,
        'coverage_pct': (round(have / total_subcaps * 100, 1)
                         if total_subcaps else None),
        'basis': 'the run\'s own engagement set',
    }


def merge(checkpoint_dir, output_path):
    """Main merge function."""
    # Load all checkpoints
    files = load_checkpoint_files(checkpoint_dir)
    if not files:
        print(f"ERROR: No evidence index files found in {checkpoint_dir}")
        return None

    print(f"Found {len(files)} checkpoint files")

    # Collect all evidence items
    all_items = []
    for f in files:
        items = f['data'].get('evidence_items', [])
        all_items.extend(items)
        print(f"  {f['filename']}: {len(items)} items")

    print(f"Total items before dedup: {len(all_items)}")

    # Deduplicate
    unique_items, duplicates = deduplicate_evidence(all_items)
    print(f"After dedup: {len(unique_items)} unique ({len(duplicates)} merged)")

    # Build subcap map
    subcap_map = build_subcap_evidence_map(unique_items)

    # Identify corroboration/contradictions
    corr_pairs, contra_pairs = identify_corroboration(unique_items)
    print(f"Corroboration pairs: {len(corr_pairs)}")
    print(f"Contradiction pairs: {len(contra_pairs)}")

    # Recalculate ERS
    unique_items = recalculate_ers(unique_items, corr_pairs)

    # Coverage stats
    coverage = calculate_coverage_stats(subcap_map)
    print(f"Coverage: {coverage['coverage_pct']}% ({coverage['with_evidence']}/{coverage['total_subcaps']})")
    print(f"  Ready (≥3): {coverage['ready_3plus']}")
    print(f"  Thin (1-2): {coverage['thin_1_2']}")
    print(f"  No evidence: {coverage['no_evidence']}")

    # Build merged index
    merged = {
        '$schema': 'dma_evidence_index_v2_merged',
        'metadata': {
            'merge_date': datetime.now().isoformat(),
            'source_files': [f['filename'] for f in files],
            'total_evidence_items': len(unique_items),
            'total_facts': sum(len(i.get('facts', [])) for i in unique_items),
            'duplicates_merged': len(duplicates),
            'corroboration_pairs': len(corr_pairs),
            'contradiction_pairs': len(contra_pairs),
            'coverage': coverage
        },
        'evidence_items': unique_items,
        'subcap_evidence_map': subcap_map,
        'corroboration_pairs': corr_pairs,
        'contradiction_pairs': contra_pairs,
        'duplicates_log': duplicates
    }

    # Save
    with open(output_path, 'w') as f:
        json.dump(merged, f, indent=2)
    print(f"\nMerged index saved to: {output_path}")
    return merged


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Merge DMA evidence checkpoints')
    parser.add_argument('checkpoint_dir', help='Directory containing checkpoint files')
    parser.add_argument('--output', default='merged_evidence_index.json',
                        help='Output file path')
    args = parser.parse_args()
    merge(args.checkpoint_dir, args.output)
