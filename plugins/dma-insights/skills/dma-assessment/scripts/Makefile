# DMA Assessment Automation Script Suite Makefile
#
# Targets: ingest, index, queries, run, audit, eval, all, clean
#
# Usage:
#   make all DOCS_ROOT=/path/to/docs INSTITUTION="My Bank"
#   make run INSTITUTION="My Bank" SUB_VERTICAL="Credit Union"
#   make audit
#   make clean

# Configuration
DOCS_ROOT ?= ./documents
INSTITUTION ?= Test_Institution
SUB_VERTICAL ?= Credit Union
SIZE_TIER ?= Mega
OUT_DIR ?= ./assessment_output
INDEX_DIR ?= ./index
CORPUS_FILE ?= evidence_corpus.parquet
QUERIES_FILE ?= subcap_queries.json
WORKBOOK_FILE ?= $(OUT_DIR)/assessment_workbook.xlsx

# Paths
SCRIPTS_DIR := $(shell pwd)
PILLAR_DIR ?= /mnt/project

# Python
PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin

# Phony targets
.PHONY: all ingest index queries run audit eval clean help install requirements

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)DMA Assessment Automation Script Suite$(NC)"
	@echo ""
	@echo "Available targets:"
	@echo "  $(GREEN)install$(NC)      - Install dependencies"
	@echo "  $(GREEN)ingest$(NC)       - Ingest documents into corpus"
	@echo "  $(GREEN)index$(NC)        - Build BM25 retrieval index"
	@echo "  $(GREEN)queries$(NC)      - Generate subcapability queries"
	@echo "  $(GREEN)run$(NC)          - Run batch assessment scoring"
	@echo "  $(GREEN)audit$(NC)        - Run QA audit on workbook"
	@echo "  $(GREEN)eval$(NC)         - Evaluate retrieval quality"
	@echo "  $(GREEN)all$(NC)          - Run all targets: ingest->index->queries->run->audit"
	@echo "  $(GREEN)clean$(NC)        - Remove generated files"
	@echo "  $(GREEN)help$(NC)         - Show this message"
	@echo ""
	@echo "Configuration variables:"
	@echo "  DOCS_ROOT=$(DOCS_ROOT)        - Root directory to ingest documents from"
	@echo "  INSTITUTION=$(INSTITUTION)    - Institution name for assessment"
	@echo "  SUB_VERTICAL=$(SUB_VERTICAL)  - Sub-vertical (Credit Union, Regional Bank, etc.)"
	@echo "  SIZE_TIER=$(SIZE_TIER)        - Size tier (Mega, Large, Medium, Small)"
	@echo "  OUT_DIR=$(OUT_DIR)            - Output directory for results"
	@echo "  PILLAR_DIR=$(PILLAR_DIR)      - Path to Pillar XLSX files"
	@echo ""
	@echo "Example:"
	@echo "  make all DOCS_ROOT=/path/to/docs INSTITUTION='My Bank' SUB_VERTICAL='Credit Union'"
	@echo "  make run INSTITUTION='My Bank' SUB_VERTICAL='Regional Bank' SIZE_TIER='Large'"

install:
	@echo "$(BLUE)Installing dependencies...$(NC)"
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r $(SCRIPTS_DIR)/requirements.txt
	@echo "$(GREEN)Dependencies installed$(NC)"

requirements:
	@echo "$(BLUE)Dependencies required:$(NC)"
	@cat $(SCRIPTS_DIR)/requirements.txt

ingest:
	@echo "$(BLUE)Ingesting documents from $(DOCS_ROOT)...$(NC)"
	@if [ ! -d "$(DOCS_ROOT)" ]; then \
		echo "$(RED)Error: DOCS_ROOT=$(DOCS_ROOT) does not exist$(NC)"; \
		exit 1; \
	fi
	$(PYTHON) $(SCRIPTS_DIR)/ingest_evidence.py \
		--root "$(DOCS_ROOT)" \
		--out "$(CORPUS_FILE)" \
		--chunk-size 1200 \
		--overlap 200
	@echo "$(GREEN)Corpus created: $(CORPUS_FILE)$(NC)"

index: ingest
	@echo "$(BLUE)Building BM25 index...$(NC)"
	@mkdir -p "$(INDEX_DIR)"
	$(PYTHON) $(SCRIPTS_DIR)/build_index.py \
		--corpus "$(CORPUS_FILE)" \
		--out-dir "$(INDEX_DIR)" \
		--force-rebuild
	@echo "$(GREEN)Index created in: $(INDEX_DIR)$(NC)"

queries: ingest
	@echo "$(BLUE)Generating subcapability queries...$(NC)"
	@if [ ! -d "$(PILLAR_DIR)" ]; then \
		echo "$(RED)Error: PILLAR_DIR=$(PILLAR_DIR) does not exist$(NC)"; \
		exit 1; \
	fi
	$(PYTHON) $(SCRIPTS_DIR)/subcap_query_builder.py \
		--pillar-dir "$(PILLAR_DIR)" \
		--out "$(QUERIES_FILE)"
	@echo "$(GREEN)Queries created: $(QUERIES_FILE)$(NC)"

run: index queries
	@echo "$(BLUE)Running assessment for $(INSTITUTION) ($(SUB_VERTICAL), $(SIZE_TIER))...$(NC)"
	@mkdir -p "$(OUT_DIR)"
	$(PYTHON) $(SCRIPTS_DIR)/assessment_runner.py \
		--corpus "$(CORPUS_FILE)" \
		--index-dir "$(INDEX_DIR)" \
		--pillar-dir "$(PILLAR_DIR)" \
		--institution "$(INSTITUTION)" \
		--sub-vertical "$(SUB_VERTICAL)" \
		--size-tier "$(SIZE_TIER)" \
		--out-dir "$(OUT_DIR)"
	@echo "$(GREEN)Assessment complete: $(OUT_DIR)$(NC)"

audit: run
	@echo "$(BLUE)Running QA audit...$(NC)"
	@if [ ! -f "$(WORKBOOK_FILE)" ]; then \
		echo "$(RED)Error: Workbook not found at $(WORKBOOK_FILE)$(NC)"; \
		exit 1; \
	fi
	$(PYTHON) $(SCRIPTS_DIR)/qa_auditor.py \
		--workbook "$(WORKBOOK_FILE)" \
		--out-dir "$(OUT_DIR)/qa_results"
	@echo "$(GREEN)QA audit complete: $(OUT_DIR)/qa_results$(NC)"

eval:
	@echo "$(BLUE)Evaluating retrieval quality...$(NC)"
	@if [ ! -f "test_queries.json" ]; then \
		echo "$(RED)Error: test_queries.json not found$(NC)"; \
		exit 1; \
	fi
	$(PYTHON) $(SCRIPTS_DIR)/eval_retrieval.py \
		--labeled-set test_queries.json \
		--index-dir "$(INDEX_DIR)" \
		--out "$(OUT_DIR)/eval_results.json"
	@echo "$(GREEN)Retrieval evaluation complete: $(OUT_DIR)/eval_results.json$(NC)"

all: ingest index queries run audit
	@echo "$(GREEN)✓ Full pipeline complete!$(NC)"
	@echo ""
	@echo "Outputs:"
	@echo "  - Corpus: $(CORPUS_FILE)"
	@echo "  - Index: $(INDEX_DIR)/"
	@echo "  - Queries: $(QUERIES_FILE)"
	@echo "  - Assessment: $(OUT_DIR)/"
	@echo "  - QA Results: $(OUT_DIR)/qa_results/"

clean:
	@echo "$(BLUE)Cleaning up generated files...$(NC)"
	rm -f $(CORPUS_FILE)
	rm -rf $(INDEX_DIR)
	rm -f $(QUERIES_FILE)
	rm -rf $(OUT_DIR)
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)Cleaned$(NC)"

# Development targets
test:
	@echo "$(BLUE)Running tests...$(NC)"
	$(PYTHON) -m pytest tests/ -v

lint:
	@echo "$(BLUE)Linting Python code...$(NC)"
	$(PYTHON) -m pylint $(SCRIPTS_DIR)/*.py

format:
	@echo "$(BLUE)Formatting Python code...$(NC)"
	$(PYTHON) -m black $(SCRIPTS_DIR)/*.py

.PHONY: test lint format

# Display configuration
print-config:
	@echo "$(BLUE)Configuration:$(NC)"
	@echo "  DOCS_ROOT: $(DOCS_ROOT)"
	@echo "  INSTITUTION: $(INSTITUTION)"
	@echo "  SUB_VERTICAL: $(SUB_VERTICAL)"
	@echo "  SIZE_TIER: $(SIZE_TIER)"
	@echo "  OUT_DIR: $(OUT_DIR)"
	@echo "  INDEX_DIR: $(INDEX_DIR)"
	@echo "  PILLAR_DIR: $(PILLAR_DIR)"
	@echo "  CORPUS_FILE: $(CORPUS_FILE)"
	@echo "  QUERIES_FILE: $(QUERIES_FILE)"

.PHONY: print-config
