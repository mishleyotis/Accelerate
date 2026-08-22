#!/usr/bin/env python3
"""
Retrieval Quality Evaluation Harness for DMA Assessment.

Loads labeled test set, runs retrieval, computes metrics.
Compares against baseline. Outputs detailed evaluation report.

Metrics: recall@5, recall@10, recall@20, MRR, tier_diversity, recency_coverage

Usage:
    python eval_retrieval.py \
        --labeled-set ./test_queries.json \
        --index-dir ./index \
        --out ./eval_results.json

Expected labeled-set JSON format:
    {
        "queries": [
            {
                "query": "digital transformation strategy",
                "expected_source_ids": ["SRC-000001", "SRC-000002"]
            }
        ]
    }
"""

import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RetrievalEvaluator:
    """Evaluate retrieval quality against labeled test sets."""

    def __init__(self, index_dir: str):
        """Initialize evaluator with index.

        Args:
            index_dir: Path to index directory with texts.parquet
        """
        self.index_dir = Path(index_dir)

        # Load texts index
        texts_path = self.index_dir / "texts.parquet"
        if not texts_path.exists():
            raise FileNotFoundError(f"texts.parquet not found in {index_dir}")

        self.texts_df = pd.read_parquet(texts_path)
        logger.info(f"Loaded {len(self.texts_df)} indexed chunks")

        # Import retriever
        # This would normally be done differently, but for now we create a simple one
        self.retriever = None
        self._init_retriever()

    def _init_retriever(self):
        """Initialize retriever (stub for now)."""
        # In real usage, import from retrieve.py
        logger.info("Initializing retriever (stub)")
        # self.retriever = Retriever(str(self.index_dir))

    def load_labeled_set(self, labeled_set_path: str) -> List[Dict[str, Any]]:
        """Load labeled test set."""
        logger.info(f"Loading labeled set from {labeled_set_path}")

        with open(labeled_set_path) as f:
            data = json.load(f)

        queries = data.get("queries", [])
        logger.info(f"Loaded {len(queries)} test queries")

        return queries

    def stub_search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        """Stub search function (returns first k chunks)."""
        # This is a placeholder; replace with actual retriever
        results = []

        for idx, row in self.texts_df.head(k).iterrows():
            results.append({
                "chunk_id": row["chunk_id"],
                "source_id": row["source_id"],
                "tier": row["tier"],
                "score": 1.0 - (idx / k),  # Fake descending score
            })

        return results

    def compute_recall_at_k(
        self,
        retrieved_ids: List[str],
        expected_ids: List[str],
        k: int,
    ) -> float:
        """Compute recall@k.

        Args:
            retrieved_ids: Retrieved source IDs (top k)
            expected_ids: Expected/relevant source IDs
            k: Cutoff

        Returns:
            Recall@k (0-1)
        """
        retrieved_set = set(retrieved_ids[:k])
        expected_set = set(expected_ids)

        if not expected_set:
            return 1.0  # All relevant items found (vacuously true)

        intersection = retrieved_set & expected_set
        return len(intersection) / len(expected_set)

    def compute_mrr(self, retrieved_ids: List[str], expected_ids: List[str]) -> float:
        """Compute Mean Reciprocal Rank.

        Returns:
            MRR (0-1), higher is better
        """
        expected_set = set(expected_ids)

        for rank, source_id in enumerate(retrieved_ids, start=1):
            if source_id in expected_set:
                return 1.0 / rank

        return 0.0  # No relevant items in top-k

    def compute_tier_diversity_score(
        self,
        results: List[Dict[str, Any]],
    ) -> float:
        """Compute tier diversity score.

        Measures how well-distributed results are across tiers (T1-T5).
        Higher is better.

        Returns:
            Score 0-1
        """
        tier_counts = {}

        for result in results:
            tier = result.get("tier", "UNKNOWN")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        # Ideal: 1 T1, 2 T2, 2 T3, 2 T4, 1 T5 (for k=8)
        # Measure entropy
        total = sum(tier_counts.values())
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in tier_counts.values():
            if count > 0:
                prob = count / total
                entropy -= prob * (prob ** 0.5)  # Custom entropy-like measure

        # Normalize
        max_entropy = 0.5  # Empirical max
        diversity = min(entropy / max_entropy, 1.0)

        return round(diversity, 3)

    def compute_recency_coverage(
        self,
        results: List[Dict[str, Any]],
    ) -> float:
        """Compute recency coverage.

        Measures how much of results are from recent sources.

        Returns:
            Score 0-1 (higher = more recent)
        """
        # Would need actual dates in results
        # For now, return stub value
        return 0.7

    def evaluate_query(
        self,
        query: str,
        expected_ids: List[str],
        k_values: List[int] = [5, 10, 20],
    ) -> Dict[str, Any]:
        """Evaluate a single query."""
        logger.info(f"Evaluating: {query}")

        # Retrieve results
        results = self.stub_search(query, k=max(k_values))
        retrieved_ids = [r["source_id"] for r in results]

        # Compute metrics
        metrics = {
            "query": query,
            "expected_count": len(expected_ids),
            "retrieved_count": len(results),
        }

        # Recall@k
        for k in k_values:
            recall = self.compute_recall_at_k(retrieved_ids, expected_ids, k)
            metrics[f"recall@{k}"] = round(recall, 3)

        # MRR
        metrics["mrr"] = round(self.compute_mrr(retrieved_ids, expected_ids), 3)

        # Tier diversity
        metrics["tier_diversity"] = self.compute_tier_diversity_score(results)

        # Recency coverage
        metrics["recency_coverage"] = self.compute_recency_coverage(results)

        return metrics

    def evaluate_all(
        self,
        labeled_set: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluate all queries in test set."""
        logger.info("Running evaluation")

        all_metrics = []

        for test_case in labeled_set:
            query = test_case.get("query", "")
            expected_ids = test_case.get("expected_source_ids", [])

            if not query:
                logger.warning("Skipping test case with no query")
                continue

            metrics = self.evaluate_query(query, expected_ids)
            all_metrics.append(metrics)

        # Aggregate
        if not all_metrics:
            logger.error("No metrics computed")
            return {}

        # Compute averages
        recall_5_avg = sum(m["recall@5"] for m in all_metrics) / len(all_metrics)
        recall_10_avg = sum(m["recall@10"] for m in all_metrics) / len(all_metrics)
        recall_20_avg = sum(m["recall@20"] for m in all_metrics) / len(all_metrics)
        mrr_avg = sum(m["mrr"] for m in all_metrics) / len(all_metrics)
        diversity_avg = sum(m["tier_diversity"] for m in all_metrics) / len(all_metrics)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "test_cases": len(all_metrics),
            "summary_metrics": {
                "recall@5": round(recall_5_avg, 3),
                "recall@10": round(recall_10_avg, 3),
                "recall@20": round(recall_20_avg, 3),
                "mrr": round(mrr_avg, 3),
                "tier_diversity": round(diversity_avg, 3),
            },
            "per_query_metrics": all_metrics,
        }

        return summary

    def compare_to_baseline(self, current: Dict, baseline: Optional[Dict]) -> Dict:
        """Compare current metrics to baseline."""
        if not baseline:
            return {"baseline_available": False}

        current_summary = current.get("summary_metrics", {})
        baseline_summary = baseline.get("summary_metrics", {})

        deltas = {}

        for metric in current_summary.keys():
            current_val = current_summary.get(metric, 0)
            baseline_val = baseline_summary.get(metric, 0)

            delta = current_val - baseline_val
            percent_change = (delta / baseline_val * 100) if baseline_val else 0

            deltas[metric] = {
                "current": current_val,
                "baseline": baseline_val,
                "delta": round(delta, 3),
                "percent_change": round(percent_change, 1),
            }

        return {
            "baseline_available": True,
            "baseline_timestamp": baseline.get("timestamp"),
            "deltas": deltas,
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate retrieval quality against labeled test set."
    )
    parser.add_argument(
        "--labeled-set",
        required=True,
        help="Path to labeled test set JSON",
    )
    parser.add_argument(
        "--index-dir",
        required=True,
        help="Path to retrieval index directory",
    )
    parser.add_argument(
        "--baseline",
        help="Path to baseline eval results JSON for comparison",
    )
    parser.add_argument(
        "--out",
        default="eval_results.json",
        help="Output results JSON path",
    )

    args = parser.parse_args()

    # Validate inputs
    if not Path(args.labeled_set).exists():
        logger.error(f"Labeled set not found: {args.labeled_set}")
        sys.exit(1)

    if not Path(args.index_dir).exists():
        logger.error(f"Index directory not found: {args.index_dir}")
        sys.exit(1)

    # Initialize evaluator
    evaluator = RetrievalEvaluator(args.index_dir)

    # Load test set
    labeled_set = evaluator.load_labeled_set(args.labeled_set)

    # Evaluate
    results = evaluator.evaluate_all(labeled_set)

    # Load baseline if provided
    baseline = None
    if args.baseline:
        logger.info(f"Loading baseline from {args.baseline}")
        with open(args.baseline) as f:
            baseline = json.load(f)

    # Compare to baseline
    comparison = evaluator.compare_to_baseline(results, baseline)
    results["comparison"] = comparison

    # Save results
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Results saved to {args.out}")

    # Print summary
    summary = results.get("summary_metrics", {})
    logger.info("Evaluation Summary:")
    for metric, value in summary.items():
        logger.info(f"  {metric}: {value}")


if __name__ == "__main__":
    main()
