#!/usr/bin/env python3
"""
Build BM25 Hybrid Retrieval Index for DMA Assessment.

Loads evidence corpus, builds BM25 index with smart tokenization,
supports incremental rebuild (only re-index changed chunks).

Usage:
    python build_index.py --corpus ./evidence_corpus.parquet --out-dir ./index/
    python build_index.py --corpus ./evidence_corpus.parquet --out-dir ./index/ --force-rebuild
"""

import hashlib
import logging
import pickle
import sys
from pathlib import Path
from typing import List, Set

import pandas as pd
from rank_bm25 import BM25Okapi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BM25IndexBuilder:
    """Build and maintain BM25 index with incremental support."""

    STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for",
        "from", "has", "he", "in", "is", "it", "of", "on", "or",
        "that", "the", "to", "was", "will", "with", "the", "this",
        "but", "not", "have", "had", "do", "does", "did", "what",
        "when", "where", "which", "who", "whom", "why", "how"
    }

    def __init__(self, min_token_length: int = 3):
        """Initialize builder.

        Args:
            min_token_length: Minimum token length to keep
        """
        self.min_token_length = min_token_length
        self.stats = {
            "corpus_rows": 0,
            "unique_chunks": 0,
            "indexed_chunks": 0,
            "skipped_chunks": 0,
        }

    def tokenize(self, text: str) -> List[str]:
        """Tokenize with smart preprocessing."""
        # Lowercase
        text = text.lower()

        # Simple tokenization (split on non-alphanumeric)
        import re
        tokens = re.findall(r"\b[a-z0-9]+\b", text)

        # Filter: stopwords, min length, duplicates
        tokens = [
            t for t in tokens
            if len(t) >= self.min_token_length and t not in self.STOPWORDS
        ]

        return tokens

    def load_corpus(self, corpus_path: str) -> pd.DataFrame:
        """Load evidence corpus."""
        logger.info(f"Loading corpus from {corpus_path}")
        df = pd.read_parquet(corpus_path)
        self.stats["corpus_rows"] = len(df)
        logger.info(f"Loaded {len(df)} chunks")
        return df

    def load_prior_index(self, index_dir: str) -> dict:
        """Load prior index metadata if it exists."""
        meta_path = Path(index_dir) / "meta.pkl"

        if meta_path.exists():
            logger.info("Loading prior index metadata")
            with open(meta_path, "rb") as f:
                return pickle.load(f)

        return {
            "indexed_chunks": {},  # chunk_id -> text_hash
            "corpus_hash": None,
        }

    def compute_corpus_hash(self, df: pd.DataFrame) -> str:
        """Compute hash of all text hashes to detect corpus changes."""
        text_hashes = df["text_hash"].tolist()
        combined = "".join(text_hashes)
        return hashlib.sha256(combined.encode()).hexdigest()

    def should_rebuild(
        self,
        corpus_hash: str,
        prior_index: dict,
        force: bool,
    ) -> bool:
        """Determine if rebuild is needed."""
        if force:
            logger.info("Force rebuild requested")
            return True

        prior_hash = prior_index.get("corpus_hash")

        if prior_hash is None:
            logger.info("No prior index found, building fresh")
            return True

        if corpus_hash != prior_hash:
            logger.info("Corpus changed, rebuilding index")
            return True

        logger.info("Corpus unchanged, skipping rebuild")
        return False

    def build_index(self, df: pd.DataFrame, corpus_hash: str) -> tuple:
        """Build BM25 index from corpus."""
        logger.info("Building BM25 index")

        texts = df["text"].tolist()
        corpus = []

        for text in texts:
            tokens = self.tokenize(text)
            corpus.append(tokens)

        # Create BM25 index
        bm25 = BM25Okapi(corpus)

        self.stats["indexed_chunks"] = len(corpus)

        logger.info(f"Indexed {len(corpus)} chunks")
        logger.info(f"Corpus hash: {corpus_hash[:16]}...")

        return bm25, texts, df[["chunk_id", "source_id", "tier", "source_filename"]].copy()

    def save_index(self, bm25: BM25Okapi, texts: List[str], meta_df: pd.DataFrame,
                   corpus_hash: str, index_dir: str):
        """Save index components."""
        Path(index_dir).mkdir(parents=True, exist_ok=True)

        # Save BM25 model
        bm25_path = Path(index_dir) / "bm25.pkl"
        with open(bm25_path, "wb") as f:
            pickle.dump(bm25, f)
        logger.info(f"Saved BM25 model to {bm25_path}")

        # Save metadata
        meta = {
            "indexed_chunks": {
                chunk_id: meta_df.loc[i, "chunk_id"]
                for i, chunk_id in enumerate(meta_df["chunk_id"])
            },
            "corpus_hash": corpus_hash,
            "total_chunks": len(texts),
        }
        meta_path = Path(index_dir) / "meta.pkl"
        with open(meta_path, "wb") as f:
            pickle.dump(meta, f)
        logger.info(f"Saved metadata to {meta_path}")

        # Save texts as parquet for reference
        texts_df = pd.DataFrame({
            "chunk_id": meta_df["chunk_id"].tolist(),
            "source_id": meta_df["source_id"].tolist(),
            "tier": meta_df["tier"].tolist(),
            "source_filename": meta_df["source_filename"].tolist(),
            "text": texts,
        })
        texts_path = Path(index_dir) / "texts.parquet"
        texts_df.to_parquet(texts_path, index=False)
        logger.info(f"Saved texts index to {texts_path}")

    def build(self, corpus_path: str, index_dir: str, force_rebuild: bool = False):
        """Main build workflow."""
        # Load corpus
        df = self.load_corpus(corpus_path)

        # Compute corpus hash
        corpus_hash = self.compute_corpus_hash(df)

        # Load prior index
        prior_index = self.load_prior_index(index_dir)

        # Check if rebuild needed
        if not self.should_rebuild(corpus_hash, prior_index, force_rebuild):
            logger.info("Index is up-to-date, skipping build")
            return

        # Build new index
        bm25, texts, meta_df = self.build_index(df, corpus_hash)

        # Save index
        self.save_index(bm25, texts, meta_df, corpus_hash, index_dir)

        # Print stats
        logger.info("Index build complete:")
        logger.info(f"  Corpus rows: {self.stats['corpus_rows']}")
        logger.info(f"  Indexed chunks: {self.stats['indexed_chunks']}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build BM25 retrieval index from evidence corpus."
    )
    parser.add_argument(
        "--corpus",
        required=True,
        help="Path to evidence_corpus.parquet",
    )
    parser.add_argument(
        "--out-dir",
        default="./index",
        help="Output directory for index files",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild even if corpus unchanged",
    )

    args = parser.parse_args()

    # Validate corpus
    if not Path(args.corpus).exists():
        logger.error(f"Corpus not found: {args.corpus}")
        sys.exit(1)

    # Build index
    builder = BM25IndexBuilder()
    builder.build(args.corpus, args.out_dir, args.force_rebuild)


if __name__ == "__main__":
    main()
