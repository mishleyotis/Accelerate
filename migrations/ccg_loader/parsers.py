"""Per-tab parsers for the shipped v7.0 pillar workbooks.

Each parser returns (rows, warnings). Headers are matched by exact name
first, then by prefix — the shipped workbooks truncate some headers and
suffix others ("Core_Score (max 5)"), and per-pillar tabs embed the
pillar number ("P1_Themes"). Grain ids derive from the Sub_Cap_ID itself:
P1C2.3.4 → pillar P1 · category P1C2 · capability P1C2.3.
"""
import re

# Segments are numeric ("P1C1.3.2") or sub-vertical variants — the V7
# schema's T2 variant cells ("P1C1.3.CU1", "P2C1.1.CIB1"): code + ordinal.
SUBCAP_RE = re.compile(r"^P\d+C\d+(?:\.(?:\d+|[A-Z]+\d+))+$")
GRAIN_RE = re.compile(r"^(P\d+)(C\d+)\.(\d+|[A-Z]+\d+)")
VC_STAGE_SEP = re.compile(r"[│|▌\n]")
SUBVERTICAL_CODES = {
    "Retail Banking": "RB", "Credit Unions": "CU", "Commercial Lending": "CL",
    "Corp & Investment Banking": "CIB", "Farm Credit / Ag Lending": "FC",
    "Asset & Wealth Management": "AM", "RIA / Broker-Dealer": "RIA",
    "Insurance Carriers": "IC", "Insurance Brokerages": "IB",
}


def _norm(name: str) -> str:
    """Header normalisation so generations match: 'Sub_Cap_ID', 'Sub-Cap ID'
    and 'SubCap ID' are one header; 'M1 - Foundational' matches the M1_
    prefix. Non-alphanumerics collapse to single underscores, lowercased."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", name.strip())).strip("_").lower()


def _headers(ws, anchor=None, max_scan=8):
    """Map normalised header name -> column index; header row by anchor."""
    anchors = tuple(_norm(a) for a in (anchor if isinstance(anchor, tuple) else (anchor,))) if anchor else ()
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1):
        names = {}
        for i, v in enumerate(row):
            if v is not None and str(v).strip():
                names.setdefault(_norm(str(v)), i)
        if not anchors or any(a in names for a in anchors):
            if len(names) >= 3:
                return names, r + 1
    return {}, 2


def _get(row, headers, *names, prefix_ok=True):
    for n in names:
        k = _norm(n)
        if k in headers:
            i = headers[k]
            return row[i] if i < len(row) else None
    if prefix_ok:
        for n in names:
            k = _norm(n)
            for h, i in headers.items():
                if h.startswith(k):
                    return row[i] if i < len(row) else None
    return None


def _s(row, headers, *names, limit=None):
    v = _get(row, headers, *names)
    if v is None:
        return None
    s = str(v).strip()
    if limit:
        s = s[:limit]
    return s or None


def _i(row, headers, *names):
    v = _get(row, headers, *names)
    try:
        return int(float(v)) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _split(value):
    if not value:
        return []
    return [p.strip() for p in re.split(r"[;,|\n]", str(value)) if p.strip()]


def _grain(subcap_id):
    m = GRAIN_RE.match(subcap_id)
    if not m:
        return None, None, None
    pillar, cat, cap = m.group(1), m.group(1) + m.group(2), None
    cap = f"{pillar}{m.group(2)}.{m.group(3)}"
    return pillar, cat, cap


def _rows(ws, headers, first):
    for row in ws.iter_rows(min_row=first, values_only=True):
        if any(c is not None and str(c).strip() for c in row):
            yield row


def parse_capability_map(ws, version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID",))
    out, warns = [], []
    for row in _rows(ws, headers, first):
        sid = _s(row, headers, "Sub_Cap_ID")
        if not sid or not SUBCAP_RE.match(sid):
            continue
        pillar, category, capability = _grain(sid)
        raw_weight = _get(row, headers, "Pillar_Weight", "Weight")
        try:
            weight = float(raw_weight) if raw_weight is not None and str(raw_weight).strip() else None
        except (TypeError, ValueError):
            weight = None
        out.append({
            "subcap_id": sid, "version": version, "capability_id": capability,
            "category_id": category, "pillar_id": pillar,
            "name": _s(row, headers, "Sub_Cap_Name", "Sub_Capability"),
            "weight": weight,   # v5.0 ships Pillar_Weight; v7.0 has none
            "l3_platform_areas": _split(_get(row, headers, "L3_Platforms_Addressing")),
            "l4_features": _split(_get(row, headers, "L4_Features_Available")),
        })
    return out, warns


def parse_maturity(ws, version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID",))
    out, warns = [], []
    # Long form (v5.0-era): one row per (subcap, band) with a Band column.
    if "band" in headers or "maturity_band" in headers:
        for row in _rows(ws, headers, first):
            sid = _s(row, headers, "Sub_Cap_ID")
            band = _s(row, headers, "Band", "Maturity Band")
            if not sid or not SUBCAP_RE.match(sid) or band not in ("M1", "M2", "M3", "M4", "M5"):
                continue
            out.append({"version": version, "subcap_id": sid, "band": band,
                        "narrative": _s(row, headers, "Narrative", "Description"),
                        "features": _s(row, headers, "Features", "Capabilities")})
        return out, warns
    # Wide form (v7.0 shipped): per band, first M{n}_ column = narrative,
    # second = features.
    band_cols = {}
    for band in ("M1", "M2", "M3", "M4", "M5"):
        cols = sorted((i, h) for h, i in headers.items() if h.startswith(f"{band.lower()}_"))
        if cols:
            band_cols[band] = (cols[0][0], cols[1][0] if len(cols) > 1 else None)
    if not band_cols:
        warns.append("no band columns found in either shape")
        return out, warns
    for row in _rows(ws, headers, first):
        sid = _s(row, headers, "Sub_Cap_ID")
        if not sid or not SUBCAP_RE.match(sid):
            continue
        for band, (ni, fi) in band_cols.items():
            narrative = row[ni] if ni < len(row) else None
            features = row[fi] if fi is not None and fi < len(row) else None
            if narrative is None and features is None:
                continue
            out.append({"version": version, "subcap_id": sid, "band": band,
                        "narrative": str(narrative or "").strip() or None,
                        "features": str(features or "").strip() or None})
    return out, warns


def parse_l3(ws, version, pillar_id):
    headers, first = _headers(ws, ("L3_ID",))
    out = []
    for row in _rows(ws, headers, first):
        l3 = _s(row, headers, "L3_ID", limit=64)
        if not l3 or not l3.upper().startswith("L3"):
            continue
        out.append({"version": version, "l3_id": l3,
                    "vendor": _s(row, headers, "Vendor"),
                    "platform_name": _s(row, headers, "Platform_Name"),
                    "category": _s(row, headers, "Category"),
                    "description": _s(row, headers, "Description"),
                    "setup_path": _s(row, headers, "Setup_Path"),
                    "prerequisites": _s(row, headers, "Prerequisites"),
                    "detailed_capabilities": _s(row, headers, "Detailed_Capabilities")})
    return out, []


def parse_l4(ws, version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID",))
    out = []
    for row in _rows(ws, headers, first):
        sid = _s(row, headers, "Sub_Cap_ID")
        feat = _s(row, headers, "Feature_Name", limit=300)
        if not sid or not feat or not SUBCAP_RE.match(sid):
            continue
        out.append({"version": version, "subcap_id": sid,
                    "l3_id": _s(row, headers, "L3_Platform_ID", "L3_ID", limit=64),
                    "feature_name": feat,
                    "vendor": _s(row, headers, "Vendor"),
                    "feature_type": _s(row, headers, "Feature_Type"),
                    "customization_level": _s(row, headers, "Customization_Level"),
                    "reference_url": _s(row, headers, "Reference_URL", "Configuration_Path", limit=500)})
    return out, []


def parse_user_stories(ws, version, pillar_id):
    headers, first = _headers(ws, ("Story_Key",))
    out = []
    conf_words = {"high": 0.9, "medium": 0.6, "med": 0.6, "low": 0.3}
    for row in _rows(ws, headers, first):
        key = _s(row, headers, "Story_Key", limit=64)
        sid = _s(row, headers, "Sub_Cap_ID")
        if not key or not sid:
            continue
        raw = str(_get(row, headers, "Match_Confidence") or "").strip()
        try:
            conf = float(raw)
            if 1.0 < conf <= 100.0:
                conf = conf / 100.0
        except ValueError:
            conf = conf_words.get(raw.lower())
        if conf is not None:
            conf = min(max(conf, 0.0), 1.0)
        out.append({"version": version, "story_key": key, "subcap_id": sid,
                    "source_type": _s(row, headers, "Source_Type", limit=32),
                    "source_ref": _s(row, headers, "Source_Ref", limit=256),
                    "use_case_ids": _s(row, headers, "Use_Case_IDs", limit=1000),
                    "l4_features_used": _s(row, headers, "L4_Features_Used", limit=2000),
                    "match_confidence": conf})
    return out, []


def parse_products(ws, version, pillar_id):
    headers, first = _headers(ws, ("Vendor",))
    out = []
    for row in _rows(ws, headers, first):
        vendor = _s(row, headers, "Vendor")
        name = _s(row, headers, "Component_Name", "Product_Name")   # v7 · v5
        if not vendor or not name:
            continue
        out.append({"version": version, "vendor": vendor, "product_name": name,
                    "component_type": _s(row, headers, "Component_Type", "Product_Category"),
                    "l3_platform_area": _s(row, headers, "L3_Platform_Area"),
                    "description": _s(row, headers, "Description"),
                    "source_type": _s(row, headers, "Source_Type"),
                    "reference_url": _s(row, headers, "Reference_URL", limit=500),
                    "lob": _s(row, headers, "LOB"),
                    "workflow": _s(row, headers, "Workflow"),
                    "status": _s(row, headers, "Status"),
                    "agent_id": _s(row, headers, "Agent_ID", limit=64),
                    "anchor_note": _s(row, headers, f"{pillar_id}_Relevance_Note", "P_Anchor_Note")})
    return out, []


def parse_agents(ws, version, pillar_id):
    headers, first = _headers(ws, ("Agent_ID",))
    out = []
    for row in _rows(ws, headers, first):
        aid = _s(row, headers, "Agent_ID", limit=64)
        if not aid:
            continue
        out.append({"version": version, "agent_id": aid,
                    "agent_name": _s(row, headers, "Agent_Name"),
                    "lob": _s(row, headers, "LOB"),
                    "workflow": _s(row, headers, "Workflow"),
                    "status": _s(row, headers, "Status"),
                    "source_type": _s(row, headers, "Source_Type"),
                    "parent_l3": _s(row, headers, "Parent_L3"),
                    "description": _s(row, headers, "Description"),
                    "source_url": _s(row, headers, "Source_URL", limit=500),
                    "usage_note": _s(row, headers, f"{pillar_id}_Usage_Note", "P_Usage_Note")})
    return out, []


def parse_constructs(ws, version, pillar_id):
    headers, first = _headers(ws, ("Construct_Name",))
    out = []
    for row in _rows(ws, headers, first):
        cname = _s(row, headers, "Construct_Name")
        if not cname:
            continue
        pn = pillar_id.replace("P", "")
        out.append({"version": version, "construct_name": cname,
                    "vendor": _s(row, headers, "Vendor"),
                    "description": _s(row, headers, "Description"),
                    "syntax_hint": _s(row, headers, "Syntax_Hint"),
                    "docs_url": _s(row, headers, "Docs_URL", limit=500),
                    "used_in_l4_features": _s(row, headers, "Used_In_L4_Features"),
                    "top_subcap_ids": _s(row, headers, f"Pillar_{pn}_Sub_Caps_Top5", "P_Sub_Caps_Top5")})
    return out, []


def parse_offerings(ws, version, pillar_id):
    headers, first = _headers(ws, ("Offering_ID",))
    out = []
    for row in _rows(ws, headers, first):
        oid = _s(row, headers, "Offering_ID", limit=64)
        if not oid or not oid.upper().startswith("OFF"):
            continue
        wrap = _s(row, headers, "Wrap_Around")
        out.append({"version": version, "offering_id": oid,
                    "offering_name": _s(row, headers, "Offering_Name"),
                    "category": _s(row, headers, "Category"),
                    "wrap_around": None if wrap is None else wrap.lower().startswith("y"),
                    "status": _s(row, headers, "Status"),
                    "overview": _s(row, headers, "Overview"),
                    "industry_challenge": _s(row, headers, "Industry_Challenge"),
                    "outcomes": _s(row, headers, "Outcomes"),
                    "core_capabilities": _s(row, headers, "Core_Capabilities"),
                    "tiers": _s(row, headers, "Tiers"),
                    "primary_vendors": _s(row, headers, "Primary_Vendors"),
                    "l3_platforms_used": _s(row, headers, "L3_Platforms_Used"),
                    "target_personas": _s(row, headers, "Target_Personas"),
                    "reference_url": _s(row, headers, "Reference_URL", limit=500),
                    "source_evidence": _s(row, headers, "Source_Evidence"),
                    "source_doc_section": _s(row, headers, "Source_Doc_Section")})
    return out, []


def parse_data_products(ws, version, pillar_id):
    headers, first = _headers(ws, ("Module_ID",))
    out = []
    for row in _rows(ws, headers, first):
        mid = _s(row, headers, "Module_ID", limit=64)
        if not mid or not mid.upper().startswith("DP"):
            continue
        out.append({"version": version, "module_id": mid,
                    "category": _s(row, headers, "Category"),
                    "module_name": _s(row, headers, "Module_Name"),
                    "description": _s(row, headers, "Description"),
                    "typical_pairing": _s(row, headers, "Typical_Pairing"),
                    "validation_strength": _s(row, headers, "Validation_Strength"),
                    "reference_url": _s(row, headers, "Reference_URL", limit=500),
                    "source_doc_section": _s(row, headers, "Source_Doc_Section")})
    return out, []


def parse_offering_matrix(ws, version, pillar_id):
    headers, first = _headers(ws, ("Offering_ID",))
    out = []
    for row in _rows(ws, headers, first):
        oid = _s(row, headers, "Offering_ID", limit=64)
        sid = _s(row, headers, "Sub_Cap_ID")
        if not oid or not sid or not SUBCAP_RE.match(sid):
            continue
        out.append({"version": version, "offering_id": oid, "subcap_id": sid,
                    "mapping_rationale": _s(row, headers, "Mapping_Rationale"),
                    "maturity_lift": _s(row, headers, "Maturity_Lift"),
                    "capabilities_addressing": _s(row, headers, "Capabilities_Addressing"),
                    "reference_url": _s(row, headers, "Reference_URL", limit=500)})
    return out, []


def parse_dp_matrix(ws, version, pillar_id):
    headers, first = _headers(ws, ("Module_ID",))
    out = []
    for row in _rows(ws, headers, first):
        mid = _s(row, headers, "Module_ID", limit=64)
        sid = _s(row, headers, "Sub_Cap_ID")
        if not mid or not sid or not SUBCAP_RE.match(sid):
            continue
        out.append({"version": version, "module_id": mid, "subcap_id": sid,
                    "mapping_rationale": _s(row, headers, "Mapping_Rationale"),
                    "maturity_lift": _s(row, headers, "Maturity_Lift"),
                    "reference_url": _s(row, headers, "Reference_URL", limit=500)})
    return out, []


def parse_cross_pillar(ws, version, pillar_id):
    headers, first = _headers(ws, ("Story_Key",))
    pn = pillar_id.replace("P", "")
    out = []
    for row in _rows(ws, headers, first):
        key = _s(row, headers, "Story_Key", limit=64)
        if not key:
            continue
        out.append({"version": version, "pillar_id": pillar_id, "story_key": key,
                    "origin_pillar": _s(row, headers, "Origin_Pillar", limit=8),
                    "origin_subcap_id": _s(row, headers, "Origin_SubCap_ID"),
                    "origin_l1_capability": _s(row, headers, "Origin_L1_Capability"),
                    "themes": _s(row, headers, f"P{pn}_Themes", "P_Themes"),
                    "confidence_level": _s(row, headers, "Confidence_Level", limit=16),
                    "story_title": _s(row, headers, "Story_Title"),
                    "story_summary": _s(row, headers, "Story_Summary"),
                    "linked_subcap_ids": _s(row, headers, f"Linked_P{pn}_SubCaps", "Linked_P_SubCaps"),
                    "linked_offerings": _s(row, headers, "Linked_Offerings"),
                    "source_reference": _s(row, headers, "Source_Reference")})
    return out, []


def parse_theme_mapping(ws, version, pillar_id):
    headers, first = _headers(ws, ("Theme",))
    pn = pillar_id.replace("P", "")
    out = []
    for row in _rows(ws, headers, first):
        theme = _s(row, headers, "Theme", limit=64)
        sid = _s(row, headers, f"P{pn}_Sub_Cap_ID", "P_Sub_Cap_ID", "Sub_Cap_ID")
        if not theme or not sid or not SUBCAP_RE.match(sid):
            continue
        out.append({"version": version, "theme": theme, "subcap_id": sid,
                    "mapping_rationale": _s(row, headers, "Mapping_Rationale"),
                    "reference_note": _s(row, headers, "Reference_Note")})
    return out, []


def parse_completeness(ws, version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID",))
    out = []
    for row in _rows(ws, headers, first):
        sid = _s(row, headers, "Sub_Cap_ID")
        if not sid or not SUBCAP_RE.match(sid):
            continue
        out.append({"version": version, "subcap_id": sid,
                    "stories_count": _i(row, headers, "Stories_Count"),
                    "l4_count": _i(row, headers, "L4_Count"),
                    "maturity_complete": _i(row, headers, "Maturity_Count"),
                    "l3_count": _i(row, headers, "L3_Count"),
                    "usecase_count": _i(row, headers, "UseCase_Count"),
                    "offering_count": _i(row, headers, "Offering_Count"),
                    "mapped_offerings": _s(row, headers, "Mapped_Offerings"),
                    "dataproduct_count": _i(row, headers, "DataProduct_Count"),
                    "mapped_dataproducts": _s(row, headers, "Mapped_DataProducts"),
                    "themes": _s(row, headers, "Theme"),
                    "crosspillar_stories": _i(row, headers, "CrossPillar_Stories"),
                    "core_score": _i(row, headers, "Core_Score"),
                    "extended_score": _i(row, headers, "Extended_Score"),
                    "total_score": _i(row, headers, "Total_Score"),
                    "narrative": _s(row, headers, "Customized_Completeness_Narrative", "Narrative")})
    return out, []


def parse_toggle_cascade(ws, version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID",))
    out = []
    def arrow(row, *names):
        return _i(row, headers, *[f"→{n}" for n in names], *names)
    for row in _rows(ws, headers, first):
        sid = _s(row, headers, "Sub_Cap_ID")
        if not sid or not SUBCAP_RE.match(sid):
            continue
        out.append({"version": version, "subcap_id": sid,
                    "user_stories_inactive": arrow(row, "User_Stories_Inactive"),
                    "l4_features_inactive": arrow(row, "L4_Features_Inactive"),
                    "maturity_rows_inactive": arrow(row, "Maturity_Rows_Inactive"),
                    "l3_references_affected": arrow(row, "L3_References_Affected"),
                    "offering_mappings_inactive": arrow(row, "Offering_Mappings_Inact"),
                    "dataproduct_mappings_inactive": arrow(row, "DataProduct_Mappings_In"),
                    "theme_mappings_inactive": arrow(row, "Theme_Mappings_Inactive"),
                    "coverage_rows_inactive": arrow(row, "Coverage_Rows_Inactive"),
                    "xp_stories_partial": arrow(row, "Cross_Pillar_Stories_Going_Partial", "Cross_Pillar_Stories_Go"),
                    "xp_stories_inactive": _i(row, headers, "→Cross_Pillar_Stories_Going_Inactive"),
                    "offerings_partial": arrow(row, "Offerings_Going_Partial"),
                    "dataproducts_partial": arrow(row, "DataProducts_Going_Partial"),
                    "total_cascade_footprint": _i(row, headers, "Total_Cascade_Footprint"),
                    "cascade_severity": _s(row, headers, "Cascade_Severity", limit=16)})
    return out, []


def parse_vc_mapping(ws, version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID",))
    # match full-name subvertical columns by prefix (headers may truncate)
    sv_cols = []
    for full, code in SUBVERTICAL_CODES.items():
        key = _norm(full)
        for h, i in headers.items():
            if h.startswith(key[:14]):
                sv_cols.append((code, i))
                break
    out, warns = [], []
    if not sv_cols:
        warns.append("no subvertical columns found")
        return out, warns
    for row in _rows(ws, headers, first):
        sid = _s(row, headers, "Sub_Cap_ID")
        if not sid or not SUBCAP_RE.match(sid):
            continue
        phase = _s(row, headers, "Phase_Categories")
        note = _s(row, headers, "Value_Chain_Coverage_Note")
        for code, i in sv_cols:
            cell = row[i] if i < len(row) else None
            if cell is None or not str(cell).strip():
                continue
            stages = [s.strip() for s in VC_STAGE_SEP.split(str(cell)) if s.strip()]
            if not stages:
                continue
            out.append({"version": version, "subcap_id": sid,
                        "subvertical_code": code, "value_chain_stages": stages,
                        "phase_categories": phase, "coverage_note": note})
    return out, warns


_R1_PRIOR = re.compile(r"^sub_cap_id_(v?[\d_]+)_original")


def parse_alias_bridge(ws, current_version, pillar_id):
    headers, first = _headers(ws, ("Sub_Cap_ID post rename",))
    prior_col = prior_version = None
    for name, idx in headers.items():
        m = _R1_PRIOR.match(name)
        if m:
            prior_col = idx
            v = m.group(1)
            v = v.replace("_", ".")
            prior_version = v if v.startswith("v") else f"v{v}"
            break
    out, warns = [], []
    if prior_col is None or "sub_cap_id_post_rename" not in headers:
        warns.append("alias bridge columns not recognised")
        return out, warns
    cur_col = headers["sub_cap_id_post_rename"]
    migrated = 0
    for row in _rows(ws, headers, first):
        prior = str(row[prior_col] or "").strip() if prior_col < len(row) else ""
        cur = str(row[cur_col] or "").strip() if cur_col < len(row) else ""
        if not (prior and cur and SUBCAP_RE.match(cur)):
            continue
        if prior == cur:
            migrated += 1     # same id across versions: not a rename, not stored
            continue
        out.append({"from_subcap_id": prior, "from_version": prior_version,
                    "to_subcap_id": cur, "to_version": current_version,
                    "reason": "renamed"})
    if migrated:
        warns.append(f"{migrated} same-id rows (migrated, not bridged)")
    return out, warns


def parse_qa_gates(ws, version, pillar_id):
    headers, first = _headers(ws, ("Gate_ID",))
    out = []
    for row in _rows(ws, headers, first):
        gid = _s(row, headers, "Gate_ID", limit=64)
        if not gid or "." not in gid:
            continue
        out.append({"version": version, "pillar_id": pillar_id, "gate_id": gid,
                    "category": _s(row, headers, "Category"),
                    "title": _s(row, headers, "Gate", "Title"),
                    "status": _s(row, headers, "Status", limit=32),
                    "detail": _s(row, headers, "Detail")})
    return out, []
