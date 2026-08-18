#!/usr/bin/env python3
"""
Generate search query plan from diagnostic questions.

Usage:
    python generate_query_plan.py <diagnostic_questions.json> \
        --entity "Gesa Credit Union" --subvertical "Credit Union" \
        [--output <query_plan.json>]

Reads all ~836 diagnostic questions and generates 6-10 search queries per subcap
using the 10-tier query system. Output is a structured plan that can be executed
during Batches 2-3.
"""

import argparse
import json
import os
import re
import sys


# Domain keyword maps for Signal 3 (evidence source targeting)
DOMAIN_SOURCES = {
    'strategy': ['annual report', 'investor presentation', 'press release', 'strategic plan'],
    'governance': ['proxy statement', 'board committee', 'charter', 'governance'],
    'innovation': ['fintech partnership', 'accelerator', 'innovation lab', 'patent'],
    'culture': ['Glassdoor', 'training program', 'employee', 'digital skills'],
    'esg': ['ESG report', 'sustainability', 'TCFD', 'climate risk', 'DEI'],
    'marketing': ['digital marketing', 'social media', 'marketing cloud', 'campaign'],
    'onboarding': ['account opening', 'digital enrollment', 'self-service', 'application'],
    'omnichannel': ['mobile banking', 'app store', 'contact center', 'branch'],
    'personalization': ['AI recommendation', 'next best action', 'segmentation'],
    'automation': ['RPA', 'automation', 'straight-through', 'process efficiency'],
    'fraud': ['fraud detection', 'AML', 'anti-money laundering', 'real-time monitoring'],
    'compliance': ['enforcement action', 'consent order', 'examination', 'MRA'],
    'resilience': ['business continuity', 'disaster recovery', 'vendor management'],
    'data_governance': ['CDO', 'data governance', 'data quality', 'master data'],
    'analytics': ['analytics', 'AI', 'machine learning', 'predictive model'],
    'architecture': ['core system', 'cloud migration', 'API', 'modernization', 'integration'],
    'cybersecurity': ['SOC2', 'ISO 27001', 'cybersecurity', 'data breach', 'CISO'],
}

# Synonym expansions for Signal 3
SYNONYMS = {
    'strategy': ['roadmap', 'plan', 'vision', 'blueprint', 'framework', 'agenda'],
    'automation': ['RPA', 'robotic process', 'automated', 'digital workflow', 'self-service'],
    'governance': ['oversight', 'committee', 'charter', 'accountability', 'risk appetite'],
    'innovation': ['fintech', 'startup', 'pilot', 'emerging technology', 'lab'],
    'customer': ['member', 'client', 'policyholder', 'account holder'],
    'digital': ['online', 'mobile', 'web', 'electronic', 'virtual'],
    'modernization': ['migration', 'upgrade', 'transformation', 'refresh', 'replacement'],
}

# Negative search templates by domain
NEGATIVE_TEMPLATES = {
    'strategy': '{entity} strategy failure outdated technology behind',
    'customer': '{entity} poor service complaint mobile app problems',
    'technology': '{entity} system outage legacy technology technical debt',
    'data': '{entity} data breach privacy violation data quality',
    'compliance': '{entity} enforcement action violation fine penalty',
    'operations': '{entity} manual process inefficient slow processing',
    'culture': '{entity} Glassdoor poor culture turnover',
    'security': '{entity} cybersecurity breach hack incident',
}


def classify_domain(subcap_id, subcap_name, diagnostic_q, capability):
    """Classify a subcapability into a domain for query generation."""
    text = f"{subcap_name} {diagnostic_q} {capability}".lower()
    
    domain_scores = {}
    for domain, keywords in DOMAIN_SOURCES.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            domain_scores[domain] = score
    
    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    
    # Fallback: infer from pillar
    if subcap_id.startswith('P1'):
        return 'strategy'
    elif subcap_id.startswith('P2'):
        return 'customer'
    elif subcap_id.startswith('P3'):
        return 'compliance'
    elif subcap_id.startswith('P4'):
        return 'architecture'
    return 'strategy'


def decompose_diagnostic_question(dq):
    """Extract subject, verb, qualifier from diagnostic question."""
    if not dq:
        return {'subject': '', 'verb': '', 'qualifier': '', 'evidence_target': ''}
    
    dq_lower = dq.lower().strip().rstrip('?')
    
    # Extract subject (main noun phrase after "is there" / "does" / "are")
    subject_patterns = [
        r'(?:does the (?:organization|institution|entity) have (?:a |an )?)(.*?)(?:\?|$)',
        r'(?:is there (?:a |an )?)(.*?)(?:\?|$)',
        r'(?:is (?:the |a |an )?)(.*?)(?:\?|$)',
        r'(?:are )(.*?)(?:\?|$)',
    ]
    
    subject = ''
    for pattern in subject_patterns:
        match = re.search(pattern, dq_lower)
        if match:
            subject = match.group(1).strip()
            break
    if not subject:
        # Fallback: use the whole question minus stop words
        stop_words = {'is', 'are', 'does', 'the', 'a', 'an', 'there', 'for', 'of', 'to', 'in', 'with', 'and', 'or', 'has', 'have', 'been'}
        words = [w for w in dq_lower.split() if w not in stop_words]
        subject = ' '.join(words[:6])
    
    # Extract verb/state
    verb_map = {
        'documented': 'documentation',
        'defined': 'definition',
        'measured': 'measurement',
        'tracked': 'tracking',
        'automated': 'automation',
        'integrated': 'integration',
        'formalized': 'formalization',
        'standardized': 'standardization',
        'optimized': 'optimization',
    }
    verb = ''
    for v, noun in verb_map.items():
        if v in dq_lower:
            verb = noun
            break
    
    # Extract qualifier (maturity implication)
    qualifier_map = {
        'documented': 'M2+',
        'defined process': 'M2+',
        'measured': 'M3+',
        'tracked': 'M3+',
        'automated': 'M3-M4',
        'optimized': 'M4+',
        'integrated across': 'M4+',
        'AI-powered': 'M4-M5',
        'predictive': 'M4+',
        'board oversight': 'M2+',
    }
    qualifier = 'M2+'  # default
    for pattern, level in qualifier_map.items():
        if pattern in dq_lower:
            qualifier = level
            break
    
    return {
        'subject': subject,
        'verb': verb,
        'qualifier': qualifier,
        'evidence_target': subject[:40],
    }


def generate_queries_for_subcap(entity, subcap, domain):
    """Generate 6-10 search queries for a single subcapability."""
    subcap_id = subcap['subcap_id']
    subcap_name = subcap.get('subcap_name', '')
    dq = subcap.get('diagnostic_question', '')
    capability = subcap.get('capability', '')
    
    decomp = decompose_diagnostic_question(dq)
    queries = []
    
    # Tier 1: Direct capability search (from diagnostic question)
    if decomp['subject']:
        queries.append({
            'tier': 1, 'type': 'diagnostic_decomposition',
            'query': f"{entity} {decomp['subject']}"[:60],
        })
        # Second variant with different framing
        if decomp['verb']:
            queries.append({
                'tier': 1, 'type': 'diagnostic_verb',
                'query': f"{entity} {decomp['evidence_target']} {decomp['verb']}"[:60],
            })
    
    # Tier 2: Official document search
    doc_targets = DOMAIN_SOURCES.get(domain, ['annual report'])[:2]
    for doc in doc_targets:
        queries.append({
            'tier': 2, 'type': 'document_target',
            'query': f"{entity} {doc} 2024 2025"[:60],
        })
    
    # Tier 3: Keyword variants
    domain_synonyms = SYNONYMS.get(domain, [])
    subcap_words = [w for w in subcap_name.lower().split() if len(w) > 3][:3]
    if subcap_words:
        queries.append({
            'tier': 3, 'type': 'keyword_variant',
            'query': f"{entity} {' '.join(subcap_words)}"[:60],
        })
    if domain_synonyms:
        queries.append({
            'tier': 3, 'type': 'synonym',
            'query': f"{entity} {domain_synonyms[0]}"[:60],
        })
    
    # Tier 4: Regulatory search (always include)
    queries.append({
        'tier': 4, 'type': 'regulatory',
        'query': f"{entity} regulatory examination enforcement"[:60],
    })
    
    # Tier 5: Technology/platform search
    if domain in ('architecture', 'analytics', 'automation', 'cybersecurity', 'data_governance'):
        tech_terms = DOMAIN_SOURCES.get(domain, [])[:2]
        for term in tech_terms:
            queries.append({
                'tier': 5, 'type': 'technology',
                'query': f"{entity} {term}"[:60],
            })
    
    # Tier 6: Sentiment search
    queries.append({
        'tier': 6, 'type': 'sentiment',
        'query': f"{entity} reviews {domain.replace('_', ' ')}"[:60],
    })
    
    # Escalation tiers (7-10) — generated but marked as conditional
    # Tier 7: Proxy signals
    queries.append({
        'tier': 7, 'type': 'proxy', 'conditional': True,
        'query': f"{entity} job posting {decomp['subject'][:20]}"[:60],
    })
    
    # Tier 8: Peer association
    queries.append({
        'tier': 8, 'type': 'peer_association', 'conditional': True,
        'query': f"{entity} industry award recognition {domain.replace('_', ' ')}"[:60],
    })
    
    # Tier 9: Vendor reverse
    queries.append({
        'tier': 9, 'type': 'vendor_reverse', 'conditional': True,
        'query': f"site:salesforce.com {entity}"[:60],
    })
    
    # Tier 10: Contradictory/negative
    neg_template = NEGATIVE_TEMPLATES.get(domain, '{entity} failure complaint criticism')
    queries.append({
        'tier': 10, 'type': 'contradictory',
        'query': neg_template.format(entity=entity)[:60],
    })
    
    return queries


def main():
    parser = argparse.ArgumentParser(description='Generate DMA research query plan')
    parser.add_argument('diagnostic_questions', help='Path to diagnostic_questions.json')
    parser.add_argument('--entity', required=True, help='Entity name')
    parser.add_argument('--subvertical', default='', help='Subvertical')
    parser.add_argument('--output', '-o', default=None, help='Output JSON path')
    args = parser.parse_args()
    
    with open(args.diagnostic_questions) as f:
        dq_data = json.load(f)
    
    subcaps = dq_data.get('subcaps_flat', [])
    
    # Generate query plan
    plan = {
        'entity': args.entity,
        'subvertical': args.subvertical,
        'total_subcaps': len(subcaps),
        'generated_at': str(datetime.now()) if 'datetime' in dir() else '',
        'capabilities': {},
        'query_stats': {'total_queries': 0, 'mandatory': 0, 'conditional': 0},
    }
    
    for sc in subcaps:
        domain = classify_domain(sc['subcap_id'], sc.get('subcap_name', ''),
                                sc.get('diagnostic_question', ''), sc.get('capability', ''))
        queries = generate_queries_for_subcap(args.entity, sc, domain)
        
        cap_id = sc['subcap_id'].split('.')[0]
        if cap_id not in plan['capabilities']:
            plan['capabilities'][cap_id] = {'subcaps': {}}
        
        plan['capabilities'][cap_id]['subcaps'][sc['subcap_id']] = {
            'subcap_name': sc.get('subcap_name', ''),
            'diagnostic_question': sc.get('diagnostic_question', ''),
            'domain': domain,
            'queries': queries,
        }
        
        plan['query_stats']['total_queries'] += len(queries)
        plan['query_stats']['mandatory'] += sum(1 for q in queries if not q.get('conditional'))
        plan['query_stats']['conditional'] += sum(1 for q in queries if q.get('conditional'))
    
    # Summary
    print(f"\n{'='*60}")
    print(f"QUERY PLAN GENERATED")
    print(f"{'='*60}")
    print(f"Entity:           {args.entity}")
    print(f"Subcapabilities:  {len(subcaps)}")
    print(f"Total queries:    {plan['query_stats']['total_queries']}")
    print(f"  Mandatory:      {plan['query_stats']['mandatory']}")
    print(f"  Conditional:    {plan['query_stats']['conditional']}")
    print(f"  Avg per subcap: {plan['query_stats']['total_queries']/max(len(subcaps),1):.1f}")
    
    # Output
    output_path = args.output or '/home/claude/dma_checkpoints/query_plan.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(plan, f, indent=2)
    print(f"\nSaved to: {output_path}")


if __name__ == '__main__':
    from datetime import datetime
    main()
