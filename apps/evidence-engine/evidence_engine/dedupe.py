"""Near-duplicate clustering: one press release, one origin, N copies.

WHY. A press release reaches the wires and three trade titles with a
boilerplate edit each; registered four times it is four "sources"
corroborating one voice. The card therefore carries `origin_cluster` and
`syndication_count` (CARD-CONTRACT.md §3: "a syndicated copy is ONE
origin"), and the cluster's canonical origin is the non-wire copy when one
exists — the entity's or the publisher's own page, not the syndicate's.

THE RULE. Exact duplicates (same normalised text hash) short-circuit;
otherwise MinHash (datasketch, num_perm=128, 5-word shingles over
textnorm.normalise(text)) + MinHashLSH at Jaccard 0.8 link neighbours, and
union-find turns links into clusters. origin_cluster_id = "OC-" + sha256 of
the lexically smallest url_key in the cluster [:8], so the id depends only
on membership, never on input order. Origin preference: non-wire (registry
press_release_wires) > earliest `published` > lexical url_key.

Deterministic and local: fixed MinHash seed, sorted traversal, no model.
"""
from __future__ import annotations

import hashlib
import re

from datasketch import MinHash, MinHashLSH

from . import registry
from .search import url_key
from .textnorm import normalise
from .types import Document

NUM_PERM = 128
SHINGLE = 5
THRESHOLD = 0.8
_SEED = 1


def shingles(text: str, n: int = SHINGLE) -> set[str]:
    words = re.findall(r"\S+", normalise(text))
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _minhash(text: str) -> MinHash:
    m = MinHash(num_perm=NUM_PERM, seed=_SEED)
    for s in shingles(text):
        m.update(s.encode("utf-8"))
    return m


def doc_key(doc: Document) -> str:
    return url_key(doc.url)


def cluster_id(url_keys) -> str:
    smallest = min(url_keys)
    return "OC-" + hashlib.sha256(smallest.encode("utf-8")).hexdigest()[:8]


def cluster(docs: list[Document]) -> dict[str, str]:
    """-> {url_key: origin_cluster_id}."""
    keys = sorted({doc_key(d): d for d in docs}.items())      # lexical, one per key
    if not keys:
        return {}
    parent = {k: k for k, _ in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            # keep the lexically smaller root so traversal order is irrelevant
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            parent[hi] = lo

    # 1. exact duplicates by content hash
    by_hash: dict[str, str] = {}
    for k, d in keys:
        h = hashlib.sha256(normalise(d.text).encode("utf-8")).hexdigest()
        if h in by_hash:
            union(k, by_hash[h])
        else:
            by_hash[h] = k
    # 2. near duplicates by MinHash LSH
    lsh = MinHashLSH(threshold=THRESHOLD, num_perm=NUM_PERM)
    hashes = {}
    for k, d in keys:
        if not (d.text or "").strip():
            continue
        m = _minhash(d.text)
        hashes[k] = m
        lsh.insert(k, m)
    for k in sorted(hashes):
        for other in sorted(lsh.query(hashes[k])):
            if other != k:
                union(k, other)
    groups: dict[str, list[str]] = {}
    for k, _ in keys:
        groups.setdefault(find(k), []).append(k)
    out: dict[str, str] = {}
    for members in groups.values():
        cid = cluster_id(members)
        for k in members:
            out[k] = cid
    return out


def syndication_counts(mapping: dict[str, str]) -> dict[str, int]:
    """-> {origin_cluster_id: number of copies}."""
    counts: dict[str, int] = {}
    for cid in mapping.values():
        counts[cid] = counts.get(cid, 0) + 1
    return counts


def members(mapping: dict[str, str]) -> dict[str, list[str]]:
    """-> {origin_cluster_id: [url_key, …] sorted}."""
    out: dict[str, list[str]] = {}
    for k, cid in sorted(mapping.items()):
        out.setdefault(cid, []).append(k)
    return out


def origin_of(cluster_docs: list[Document]) -> Document | None:
    """The canonical origin of one cluster: a non-wire copy first, then the
    earliest stated `published`, then the lexically smallest url_key."""
    if not cluster_docs:
        return None

    def sort_key(d: Document):
        wire = registry.is_wire(d.final_url or d.url)
        pub = d.published or "9999-99-99"
        return (1 if wire else 0, pub, doc_key(d))

    return sorted(cluster_docs, key=sort_key)[0]
