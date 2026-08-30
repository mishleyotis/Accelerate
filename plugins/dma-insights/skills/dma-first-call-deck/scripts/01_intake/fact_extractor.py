#!/usr/bin/env python3
"""
fact_extractor.py — Parse DMA assessment and client research reports into fact_bank.json.

Handles varied report formats: .docx, .pdf, .txt. Extracts all scores, pillars,
capabilities, strategic objectives, financials, and org profile data.

Usage:
    python scripts/01_intake/fact_extractor.py \
        --assessment /path/to/DMA_Assessment_Report.docx \
        --research /path/to/Client_Profile_Research_Report.docx \
        --out fact_bank.json

Safeguards:
    - Validates extracted overall score is 0-5 range
    - Validates all 4 pillar scores present
    - Validates ≥12 capability scores (warns if <17)
    - Flags missing fields as [DATA NEEDED] instead of fabricating
    - Logs extraction confidence per field (high/medium/low)
    - Handles both structured tables and prose-embedded scores
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime


def read_document(filepath):
    """Read document content. Supports .docx, .pdf, .txt."""
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == '.docx':
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(filepath)
            return result.text_content
        except ImportError:
            # Fallback: python-docx
            try:
                from docx import Document
                doc = Document(filepath)
                return "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                print("ERROR: Install markitdown[docx] or python-docx", file=sys.stderr)
                sys.exit(1)
    elif ext == '.pdf':
        try:
            import subprocess
            result = subprocess.run(
                ["pdftotext", "-layout", filepath, "-"],
                capture_output=True, text=True
            )
            return result.stdout
        except FileNotFoundError:
            print("ERROR: pdftotext not found. Install poppler-utils.", file=sys.stderr)
            sys.exit(1)
    elif ext in ('.txt', '.md'):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        print(f"ERROR: Unsupported file type: {ext}", file=sys.stderr)
        sys.exit(1)


def extract_overall_score(text):
    """Extract overall maturity score (X.XX out of 5)."""
    patterns = [
        r'Overall\s+(?:Digital\s+)?Maturity\s+Score[:\s]+(\d+\.\d+)',
        r'overall\s+score[:\s]+(\d+\.\d+)',
        r'scores?\s+(\d+\.\d+)\s*/?\s*5',
        r'Overall.*?(\d+\.\d+)\s*[—–-]\s*M\d',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            score = float(m.group(1))
            if 0 <= score <= 5:
                return score
    return None


def extract_pillar_scores(text):
    """Extract 4 pillar scores."""
    pillars = {}
    
    # Pattern: P1: Strategy... | 2.71 or P1: 2.71
    patterns = [
        r'P(\d)\s*[:\s]+([^|]+?)\s*(?:\(\d+%\))?\s*[=|:]\s*(\d+\.\d+)',
        r'P(\d)\s+[^:]+?[:\s]+(\d+\.\d+)',
        r'Pillar\s+(\d)[:\s]+([^|]+?)\s*[|:]\s*(\d+\.\d+)',
    ]
    
    for p in patterns:
        matches = re.findall(p, text[:20000])
        for m in matches:
            if len(m) == 3:
                p_num, p_name, p_score = m
            else:
                p_num, p_score = m[0], m[1]
                p_name = f"Pillar {p_num}"
            
            score = float(p_score)
            if 0 <= score <= 5 and p_num in ('1', '2', '3', '4'):
                key = f"P{p_num}"
                if key not in pillars or score != pillars[key].get('score'):
                    pillars[key] = {"score": score, "name": p_name.strip()[:50]}
    
    return pillars


def extract_capability_scores(text):
    """Extract all P#C# capability scores with peer medians."""
    capabilities = {}
    
    # Pattern: P1C1 Name: 3.04 or P1C1 Name (3.04, +0.54 vs peers)
    patterns = [
        r'(P\dC\d)\s+([^(:|]+?)\s*[:(]\s*(\d+\.\d+)',
        r'(P\dC\d)\s+([^|]+?)\s*[|]\s*(\d+\.\d+)',
    ]
    
    for p in patterns:
        matches = re.findall(p, text)
        for cap_id, name, score in matches:
            score_f = float(score)
            if 0 <= score_f <= 5:
                name_clean = re.sub(r'\*+', '', name).strip()[:60]
                if cap_id not in capabilities:
                    capabilities[cap_id] = {
                        "name": name_clean,
                        "score": score_f,
                        "peer_median": None,
                    }
    
    # Extract peer medians: "+0.54 vs peers" or "Peer Median: 2.5"
    for cap_id in capabilities:
        # Look for delta pattern near the capability
        delta_pat = re.search(
            rf'{cap_id}[^)]+?([+-]\d+\.\d+)\s*(?:vs|above|below)\s*peer',
            text, re.IGNORECASE
        )
        if delta_pat:
            delta = float(delta_pat.group(1))
            capabilities[cap_id]["peer_median"] = round(capabilities[cap_id]["score"] - delta, 2)
        
        # Direct peer median pattern
        median_pat = re.search(
            rf'{cap_id}[^.]+?[Pp]eer\s*[Mm]edian[:\s]+(\d+\.\d+)',
            text
        )
        if median_pat:
            capabilities[cap_id]["peer_median"] = float(median_pat.group(1))
    
    return capabilities


def extract_client_info(text):
    """Extract client name, HQ, assets, etc."""
    info = {}
    
    # Client name: usually in the first few lines or after "Client:"
    name_patterns = [
        r'\*\*([A-Z][A-Za-z\s]+(?:Corporation|Bank|Credit Union|Insurance|Financial|Partners)[^*]*?)\*\*',
        r'Client[:\s]+([A-Z][A-Za-z\s&]+)',
    ]
    for p in name_patterns:
        m = re.search(p, text[:2000])
        if m:
            info["client_name"] = m.group(1).strip()
            break
    
    # Subvertical
    sv_match = re.search(r'Subvertical[:\s]+(\S+\s*[—–-]\s*[^\n]+)', text[:3000])
    if sv_match:
        info["subvertical_raw"] = sv_match.group(1).strip()
    
    # Assessment date
    date_match = re.search(r'Assessment\s+Date[:\s]+([^\n]+)', text[:3000])
    if date_match:
        info["assessment_date"] = date_match.group(1).strip()
    
    # Assets
    assets = re.search(r'\$(\d+(?:\.\d+)?)\s*[Bb](?:illion)?(?:\s+(?:in\s+)?(?:total\s+)?assets)', text)
    if assets:
        info["total_assets"] = f"${assets.group(1)}B"
    
    # Branches
    branches = re.search(r'(\d{1,4})\s+branch', text, re.IGNORECASE)
    if branches:
        info["branches"] = branches.group(1)
    
    # Employees / FTE
    emp = re.search(r'(\d{1,3},?\d{3})\s+(?:employees|FTE|associates|team members)', text, re.IGNORECASE)
    if emp:
        info["employees"] = emp.group(1)
    
    # Founded
    founded = re.search(r'[Ff]ounded[:\s]+(\d{4})', text)
    if founded:
        info["founded"] = founded.group(1)
    
    # HQ
    hq = re.search(r'[Hh]eadquarters?[:\s]+([^\n|]+)', text)
    if hq:
        info["hq"] = hq.group(1).strip()
    
    return info


def extract_strategic_objectives(text):
    """Extract strategic objectives from client research report."""
    objectives = []
    
    # Look for numbered strategic objectives
    obj_pattern = re.findall(
        r'(?:Strategic\s+Objective|Obj\s*#?\d+)[:\s]+([^\n]+)',
        text, re.IGNORECASE
    )
    if obj_pattern:
        objectives.extend(obj_pattern[:5])
    
    # Look for table-formatted objectives
    table_pattern = re.findall(
        r'\|\s*\d+\s*\|\s*([^|]+?)\s*\|',
        text[:10000]
    )
    for row in table_pattern:
        if len(row) > 20 and any(kw in row.lower() for kw in ['expand', 'enhance', 'maintain', 'grow', 'improve', 'invest']):
            objectives.append(row.strip())
    
    return list(dict.fromkeys(objectives))[:5]  # Dedupe, max 5


def extract_strengths(text):
    """Extract key strengths from assessment report."""
    strengths = []
    
    # Pattern: "Key Strengths" section
    strength_section = re.search(
        r'[Kk]ey\s+[Ss]trengths?(.*?)(?:Critical\s+Gaps?|##|\Z)',
        text[:15000], re.DOTALL
    )
    if strength_section:
        section = strength_section.group(1)
        # Extract bold items or bullet points
        items = re.findall(r'\*\*([^*]+?)\*\*', section)
        strengths.extend(i.strip()[:100] for i in items if len(i.strip()) > 10)
    
    return strengths[:5]


def extract_gaps(text):
    """Extract critical gaps from assessment report."""
    gaps = []
    
    gap_section = re.search(
        r'[Cc]ritical\s+[Gg]aps?(.*?)(?:Strategic\s+Recommendation|##|\Z)',
        text[:15000], re.DOTALL
    )
    if gap_section:
        section = gap_section.group(1)
        items = re.findall(r'\*\*(P\dC\d\s+[^*]+?)\*\*', section)
        gaps.extend(i.strip()[:100] for i in items)
    
    return gaps[:5]


def build_fact_bank(assessment_text, research_text=None):
    """Build complete fact_bank from parsed texts."""
    facts = []
    fact_id = 1
    
    # Client info (prefer research report, fall back to assessment)
    source_text = research_text if research_text else assessment_text
    client = extract_client_info(source_text)
    if not client.get("client_name") and assessment_text:
        client.update(extract_client_info(assessment_text))
    
    for field, value in client.items():
        facts.append({
            "fact_id": f"F-{fact_id:03d}",
            "category": "org_profile",
            "content": f"{field}: {value}",
            "data_value": None,
            "source": {"file_id": "research" if research_text else "assessment", "location": "header"},
            "target_slides": [1, 6],
            "confidence": "high"
        })
        fact_id += 1
    
    # Overall score
    overall = extract_overall_score(assessment_text)
    if overall:
        facts.append({
            "fact_id": f"F-{fact_id:03d}",
            "category": "dma_score",
            "content": f"Overall digital maturity score: {overall}/5",
            "data_value": overall,
            "source": {"file_id": "assessment", "location": "executive_summary"},
            "target_slides": [9, 13],
            "confidence": "high"
        })
        fact_id += 1
    
    # Pillar scores
    pillars = extract_pillar_scores(assessment_text)
    for p_key, p_data in pillars.items():
        facts.append({
            "fact_id": f"F-{fact_id:03d}",
            "category": "pillar_score",
            "content": f"{p_key} {p_data['name']}: {p_data['score']}/5",
            "data_value": p_data['score'],
            "source": {"file_id": "assessment", "location": "pillar_summary"},
            "target_slides": [9, 13, 14],
            "confidence": "high"
        })
        fact_id += 1
    
    # Capability scores
    capabilities = extract_capability_scores(assessment_text)
    for cap_id, cap_data in capabilities.items():
        facts.append({
            "fact_id": f"F-{fact_id:03d}",
            "category": "capability_score",
            "content": f"{cap_id} {cap_data['name']}: {cap_data['score']}/5 (peer median: {cap_data.get('peer_median', 'unknown')})",
            "data_value": cap_data['score'],
            "source": {"file_id": "assessment", "location": f"capability_{cap_id}"},
            "target_slides": [14, 16],
            "confidence": "high" if cap_data.get('peer_median') else "medium"
        })
        fact_id += 1
    
    # Strategic objectives (from research)
    if research_text:
        objectives = extract_strategic_objectives(research_text)
        for obj in objectives:
            facts.append({
                "fact_id": f"F-{fact_id:03d}",
                "category": "strategic_objective",
                "content": obj,
                "data_value": None,
                "source": {"file_id": "research", "location": "strategic_objectives"},
                "target_slides": [6, 13],
                "confidence": "high"
            })
            fact_id += 1
    
    # Strengths
    strengths = extract_strengths(assessment_text)
    for s in strengths:
        facts.append({
            "fact_id": f"F-{fact_id:03d}",
            "category": "strength",
            "content": s,
            "data_value": None,
            "source": {"file_id": "assessment", "location": "key_strengths"},
            "target_slides": [13],
            "confidence": "high"
        })
        fact_id += 1
    
    # Gaps
    gaps = extract_gaps(assessment_text)
    for g in gaps:
        facts.append({
            "fact_id": f"F-{fact_id:03d}",
            "category": "opportunity",
            "content": g,
            "data_value": None,
            "source": {"file_id": "assessment", "location": "critical_gaps"},
            "target_slides": [16],
            "confidence": "high"
        })
        fact_id += 1
    
    # Build DMA scores summary
    dma_scores = {
        "overall": overall,
        "pillars": {k: v for k, v in pillars.items()},
        "capabilities": {k: v for k, v in capabilities.items()},
    }
    
    # Build terminology map based on sub-vertical
    sv = client.get("subvertical_raw", "").lower()
    terminology_map = {}
    if "credit union" in sv or sv == "credit_unions":
        terminology_map = {
            "Customer": "Member",
            "Customer Experience": "Member Experience",
            "Customer Experience & Engagement": "Member Experience & Engagement",
            "customers": "members",
            "CUSTOMER EXPERIENCE": "MEMBER EXPERIENCE",
            "Personalized Customer Engagement": "Personalized Member Engagement",
        }
    elif "insurance brokerage" in sv or sv == "insurance_brokerages":
        terminology_map = {
            "Customer Experience": "Client Experience",
            "Customer Experience & Engagement": "Client Experience & Engagement",
            "CUSTOMER EXPERIENCE": "CLIENT EXPERIENCE",
        }

    return {
        "metadata": {
            "client_name": client.get("client_name", "[DATA NEEDED]"),
            "subvertical": client.get("subvertical_raw", "[DATA NEEDED]"),
            "terminology_map": terminology_map,
            "source_files": [
                {"file_id": "assessment", "filename": "DMA_Assessment_Report", "type": "assessment_report"},
            ] + ([{"file_id": "research", "filename": "Client_Research_Report", "type": "client_research"}] if research_text else []),
            "extracted_at": datetime.utcnow().isoformat() + "Z",
        },
        "facts": facts,
        "dma_scores": dma_scores,
    }


def validate_fact_bank(fb):
    """Validate completeness of extracted fact bank."""
    issues = []
    
    # Check overall score
    if fb["dma_scores"]["overall"] is None:
        issues.append("CRITICAL: Overall score not found")
    
    # Check pillars
    pillar_count = len(fb["dma_scores"]["pillars"])
    if pillar_count < 4:
        issues.append(f"WARNING: Only {pillar_count}/4 pillar scores found")
    
    # Check capabilities
    cap_count = len(fb["dma_scores"]["capabilities"])
    if cap_count < 12:
        issues.append(f"WARNING: Only {cap_count} capability scores (expected 17)")
    elif cap_count < 17:
        issues.append(f"NOTE: {cap_count}/17 capability scores found")
    
    # Check client name
    if fb["metadata"]["client_name"] == "[DATA NEEDED]":
        issues.append("WARNING: Client name not extracted")
    
    # Check for strategic objectives
    obj_count = sum(1 for f in fb["facts"] if f["category"] == "strategic_objective")
    if obj_count == 0:
        issues.append("WARNING: No strategic objectives extracted (Slide 13 strengths will be generic)")
    
    return issues


def main():
    parser = argparse.ArgumentParser(description="Extract facts from DMA reports into fact_bank.json")
    parser.add_argument("--assessment", required=True, help="DMA assessment report (.docx, .pdf, .txt)")
    parser.add_argument("--research", help="Client research report (.docx, .pdf, .txt)")
    parser.add_argument("--out", default="fact_bank.json", help="Output JSON path")
    parser.add_argument("--validate", action="store_true", help="Run validation checks")
    args = parser.parse_args()
    
    # Read documents
    print(f"Reading assessment: {args.assessment}")
    assessment_text = read_document(args.assessment)
    print(f"  {len(assessment_text)} chars extracted")
    
    research_text = None
    if args.research:
        print(f"Reading research: {args.research}")
        research_text = read_document(args.research)
        print(f"  {len(research_text)} chars extracted")
    
    # Build fact bank
    fb = build_fact_bank(assessment_text, research_text)
    
    # Validate
    issues = validate_fact_bank(fb)
    
    # Summary
    print(f"\n=== EXTRACTION SUMMARY ===")
    print(f"Client: {fb['metadata']['client_name']}")
    print(f"Overall score: {fb['dma_scores']['overall']}")
    print(f"Pillars: {len(fb['dma_scores']['pillars'])}/4")
    print(f"Capabilities: {len(fb['dma_scores']['capabilities'])}/17")
    print(f"Total facts: {len(fb['facts'])}")
    
    cat_counts = {}
    for f in fb["facts"]:
        cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1
    for cat, count in sorted(cat_counts.items()):
        print(f"  {cat}: {count}")
    
    if issues:
        print(f"\n⚠ {len(issues)} validation issues:")
        for i in issues:
            print(f"  {i}")
    else:
        print("\n✓ All validations passed")
    
    # Write output
    with open(args.out, "w") as f:
        json.dump(fb, f, indent=2)
    print(f"\nWritten to {args.out}")
    
    if any("CRITICAL" in i for i in issues):
        sys.exit(1)


if __name__ == "__main__":
    main()
