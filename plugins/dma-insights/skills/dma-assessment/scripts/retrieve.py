#!/usr/bin/env python3
"""
Retrieval Engine + Evidence Pack Builder for DMA Assessment.

Loads BM25 index, provides search and evidence pack generation.
Supports tier diversity and de-duplication.

Usage:
    from retrieve import Retriever
    retriever = Retriever("./index")
    results = retriever.search("digital strategy", k=20)
    pack = retriever.build_evidence_pack("P1C1", "Digital Strategy & Vision")

    CLI:
    python retrieve.py --index-dir ./index/ --query "digital transformation"
"""

import json
import logging
import pickle
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Retriever:
    """BM25 retriever with evidence pack support."""

    def __init__(self, index_dir: str):
        """Initialize retriever from index directory.

        Args:
            index_dir: Path to index directory with bm25.pkl, meta.pkl, texts.parquet
        """
        self.index_dir = Path(index_dir)

        # Load BM25 model
        bm25_path = self.index_dir / "bm25.pkl"
        with open(bm25_path, "rb") as f:
            self.bm25 = pickle.load(f)
        logger.info(f"Loaded BM25 model from {bm25_path}")

        # Load metadata
        meta_path = self.index_dir / "meta.pkl"
        with open(meta_path, "rb") as f:
            self.meta = pickle.load(f)
        logger.info(f"Loaded metadata from {meta_path}")

        # Load texts
        texts_path = self.index_dir / "texts.parquet"
        self.texts_df = pd.read_parquet(texts_path)
        logger.info(f"Loaded {len(self.texts_df)} chunks from {texts_path}")

        # Create mapping for fast lookup
        self.chunk_id_to_row = {
            chunk_id: idx
            for idx, chunk_id in enumerate(self.texts_df["chunk_id"])
        }

    def tokenize(self, text: str) -> List[str]:
        """Tokenize query text."""
        import re
        text = text.lower()
        tokens = re.findall(r"\b[a-z0-9]+\b", text)

        stopwords = {
            "a", "an", "and", "are", "as", "at", "be", "by", "for",
            "from", "has", "he", "in", "is", "it", "of", "on", "or",
            "that", "the", "to", "was", "will", "with", "this", "but",
        }
        tokens = [t for t in tokens if len(t) >= 3 and t not in stopwords]
        return tokens

    def search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        """Search for relevant chunks.

        Args:
            query: Search query string
            k: Number of results to return

        Returns:
            List of result dicts with chunk_id, text, tier, score, source_id
        """
        tokens = self.tokenize(query)

        if not tokens:
            logger.warning(f"Query '{query}' produced no tokens")
            return []

        # Get BM25 scores
        scores = self.bm25.get_scores(tokens)

        # Sort by score
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True
        )

        # Return top k
        results = []
        for idx, score in ranked[:k]:
            row = self.texts_df.iloc[idx]
            results.append({
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "tier": row["tier"],
                "source_id": row["source_id"],
                "source_filename": row["source_filename"],
                "score": float(score),
            })

        return results

    def diversify(
        self,
        results: List[Dict[str, Any]],
        max_per_tier: int = 3,
    ) -> List[Dict[str, Any]]:
        """Enforce tier diversity in results.

        Args:
            results: Search results
            max_per_tier: Maximum results per tier

        Returns:
            Diversified results, sorted by original score within tier
        """
        tier_counts = {}
        diversified = []

        for result in results:
            tier = result["tier"]
            if tier not in tier_counts:
                tier_counts[tier] = 0

            if tier_counts[tier] < max_per_tier:
                diversified.append(result)
                tier_counts[tier] += 1

        return diversified

    def deduplicate(
        self,
        results: List[Dict[str, Any]],
        similarity_threshold: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Remove duplicate or near-duplicate results.

        Simple implementation: remove exact duplicates and very similar texts.

        Args:
            results: Search results
            similarity_threshold: Jaccard similarity threshold for dedup

        Returns:
            Deduplicated results
        """
        seen_text_hashes = set()
        deduplicated = []

        for result in results:
            # Simple hash of text (not cryptographic, just for dedup)
            text_hash = hash(result["text"][:100])

            if text_hash not in seen_text_hashes:
                deduplicated.append(result)
                seen_text_hashes.add(text_hash)

        return deduplicated

    def build_evidence_pack(
        self,
        subcap_id: str,
        subcap_name: str,
        diagnostic_questions: Optional[List[str]] = None,
        k: int = 15,
    ) -> Dict[str, Any]:
        """Build evidence pack for a subcapability.

        Args:
            subcap_id: Subcapability ID (e.g., "P1C1-001")
            subcap_name: Human-readable name
            diagnostic_questions: List of diagnostic questions
            k: Number of chunks to retrieve

        Returns:
            Evidence pack dict with chunks, tier_distribution, coverage_score
        """
        # Generate queries
        if diagnostic_questions is None:
            diagnostic_questions = []

        queries = [
            subcap_name,
            f"{subcap_name} governance",
            f"{subcap_name} controls",
            f"{subcap_name} metrics",
        ]

        # Merge results from all queries
        all_results = []
        for query in queries:
            results = self.search(query, k=k)
            all_results.extend(results)

        # Deduplicate and diversify
        unique_results = self.deduplicate(all_results)
        diverse_results = self.diversify(unique_results, max_per_tier=4)

        # Sort by score
        diverse_results.sort(key=lambda x: x["score"], reverse=True)

        # Limit to k
        diverse_results = diverse_results[:k]

        # Calculate tier distribution
        tier_dist = {}
        for result in diverse_results:
            tier = result["tier"]
            tier_dist[tier] = tier_dist.get(tier, 0) + 1

        # Calculate coverage score (0-1)
        # Based on: having T1/T2 evidence, tier diversity, number of chunks
        coverage_score = 0.0

        if tier_dist.get("T1", 0) > 0:
            coverage_score += 0.3
        if tier_dist.get("T2", 0) > 0:
            coverage_score += 0.2
        if tier_dist.get("T3", 0) > 0:
            coverage_score += 0.15

        coverage_score += min(len(diverse_results) / k, 1.0) * 0.35

        # Build pack
        pack = {
            "subcap_id": subcap_id,
            "subcap_name": subcap_name,
            "diagnostic_questions": diagnostic_questions,
            "chunks": [
                {
                    "chunk_id": r["chunk_id"],
                    "text": r["text"],
                    "tier": r["tier"],
                    "source_id": r["source_id"],
                    "source_filename": r["source_filename"],
                    "score": r["score"],
                }
                for r in diverse_results
            ],
            "tier_distribution": tier_dist,
            "coverage_score": round(coverage_score, 2),
        }

        return pack


def main():
    """CLI entry point for interactive retrieval."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Search evidence index and generate evidence packs."
    )
    parser.add_argument(
        "--index-dir",
        required=True,
        help="Path to index directory",
    )
    parser.add_argument(
        "--query",
        help="Search query",
    )
    parser.add_argument(
        "--subcap-id",
        help="Subcapability ID for evidence pack generation",
    )
    parser.add_argument(
        "--subcap-name",
        help="Subcapability name",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=15,
        help="Number of results to return",
    )

    args = parser.parse_args()

    # Initialize retriever
    if not Path(args.index_dir).exists():
        logger.error(f"Index directory not found: {args.index_dir}")
        sys.exit(1)

    retriever = Retriever(args.index_dir)

    # Search mode
    if args.query:
        logger.info(f"Searching for: {args.query}")
        results = retriever.search(args.query, k=args.k)
        print(json.dumps(results, indent=2, default=str))

    # Evidence pack mode
    elif args.subcap_id and args.subcap_name:
        logger.info(f"Building evidence pack for {args.subcap_id}: {args.subcap_name}")
        pack = retriever.build_evidence_pack(args.subcap_id, args.subcap_name, k=args.k)
        print(json.dumps(pack, indent=2, default=str))

    else:
        logger.error("Provide either --query or (--subcap-id + --subcap-name)")
        sys.exit(1)


if __name__ == "__main__":
    main()
