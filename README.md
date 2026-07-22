# Bibliometric Analyzer

**Science Lineage & Bibliometrics CLI** — A powerful command-line tool designed for academic researchers to automate end-to-end scientific literature literature mapping, live citation lineage crawling, systematic review Excel matrix generation, PRISMA flowchart modeling, and native R-Bibliometrix reporting.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![R 4.0+](https://img.shields.io/badge/R-4.0+-green.svg)](https://www.r-project.org/)

---

## Table of Contents
1. [Overview](#overview)
2. [Features & Domain Themes](#features--domain-themes)
3. [Prerequisites & Installation](#prerequisites--installation)
4. [Environment Configuration (`.env`)](#environment-configuration-env)
5. [Usage Guide](#usage-guide)
   - [🚀 End-to-End Automated Pipeline (`--pipeline`)](#-1-end-to-end-automated-pipeline--pipeline---recommended)
   - [🔄 Regenerating R Assets After Manual Excel Edits (`--r-native` / `--r-report`)](#-2-regenerating-r-assets-after-manual-excel-edits---lightweight-mode)
   - [🌳 Standalone Citation Lineage Crawling (`--linaje`)](#-3-standalone-citation-lineage-crawling--linaje)
   - [📋 Blank Excel Matrix Generation (`--generate-matrix`)](#-4-blank-excel-matrix-generation--generate-matrix)
   - [📐 Interactive PRISMA 2020 Flow Generator (`--prisma-flow`)](#-5-interactive-prisma-2020-flow-generator--prisma-flow)
6. [API Caching System](#api-caching-system)
7. [Complete CLI Reference](#complete-cli-reference)
8. [Package Architecture](#package-architecture)
9. [Running Unit Tests](#running-unit-tests)
10. [License](#license)

---

## Overview

`bibliometric-analyzer` connects to **Scopus Search API**, **NCBI PubMed Entrez API**, and the **OpenAlex Global API** in an automated cascade to crawl and synthesize citation networks.

By starting with a single **Seed DOI** or **Topic Query**, the tool executes a recursive Breadth-First Search (BFS) and PageRank centrality analysis to extract a clean academic lineage. It maps paper metadata, extracts qualitative discoveries and structural design fields, standardizes botanical species and tissue organs, groups compound author names, and bridges results straight into R script environments for bibliometric mapping and R Markdown rendering.

---

## Features & Domain Themes

The CLI supports dynamic extraction schemas tailored to specific scientific disciplines. Select your domain using the `--theme <theme>` flag:

| Theme Code (`--theme`) | Domain / Focus | Key Fields Extracted |
|---|---|---|
| `phytochemistry` | Plant Biochemistry & Bio-processes | Plant Species, Plant Part/Tissue, Elicitor/Precursor, HPLC-UV/analytical method, Yield (mg/g) |
| `health_sciences` | Medical Genomics & Clinical Trials | Study Type (RCT/Cohort/Cross-sectional), Sample Size, Intervention (CD34+, Metformin, etc.), Outcome, OR/RR/HR/$p$-value, GRADE Level of Evidence |
| `industrial_engineering` | Process Optimization | Industrial Process, Methodology (Six Sigma/DMAIC/Lean), KPI (OEE/Cpk/Lead Time), Improvement % |
| `computer_science` | AI & Software Engineering | Model Architecture, Benchmark Dataset, Metric (F1/Accuracy/Latency), Baseline |
| `general` | Multidisciplinary Studies | General Research Objectives, Methodological Design, Key Findings |

---

## Prerequisites & Installation

### 1. System Requirements
- **Python 3.8+** (with pip)
- **R / Rscript 4.0+** (Optional, required for R-Bibliometrix and R Markdown reports)
- **Pandoc** (Required for R Markdown compilation into HTML/PDF)

### 2. Installation Steps

Clone the repository and install it in editable mode:
```bash
git clone https://github.com/Joax1213/SCRIPTMETODOLOGICO.git
cd SCRIPTMETODOLOGICO
pip install -e .
```
Or install the requirements directly:
```bash
pip install -r requirements.txt
```

### 3. Check & Install R Dependencies
To verify your R installation and automatically install the required R packages (`bibliometrix`, `rmarkdown`, `htmltools`, etc.), run:
```bash
python -m bibliometric_analyzer.cli --check-r
```

---

## Environment Configuration (`.env`)

Create a `.env` file in the root folder of the project to authenticate Scopus search calls and get bypass limits:

```dotenv
# Recommended: Polite pool identifier for OpenAlex API calls
CONTACT_EMAIL=your_email@domain.com

# Required for Scopus Search (Elsevier Developer Portal Key)
SCOPUS_API_KEY=9a1993bc6ef543388e5f3fe0d1dba221

# Optional: Unlocks 10 requests/second on NCBI PubMed API
NCBI_API_KEY=your_pubmed_api_key
```

*Note: If no Scopus key is provided, the tool will dynamically fallback to PubMed and OpenAlex queries to crawl metadata.*

---

## Usage Guide

### 🚀 1. End-to-End Automated Pipeline (`--pipeline`) — Recommended

The `--pipeline` flag coordinates the full 5-stage automated research workflow:
1. **Stage 1:** Identifies the seed paper (using a DOI or topic query search).
2. **Stage 2:** Explores the lineage network recursively using a BFS crawl.
3. **Stage 3:** Builds the PRISMA diagram and compiles the systematic review Excel sheet (`matriz_auditoria_automatizada.xlsx`) with qualitative extractions.
4. **Stage 5 & 6:** Invokes R-Bibliometrix in the background to calculate keyword co-occurrences, generates a standalone HTML Vis.js interactive network (`red_coocurrencia.html`), and renders the R Markdown HTML report (`reporte_editorial.html`).

#### Examples:
```bash
# Example A: Phytochemistry (Seed DOI)
python -m bibliometric_analyzer.cli --pipeline \
  --theme phytochemistry \
  --seed-mode doi \
  --doi 10.1002/leg3.129 \
  --output-dir presentacion/prueba \
  --verbose

# Example B: Health Sciences & Clinical Genomics (Seed DOI)
python -m bibliometric_analyzer.cli --pipeline \
  --theme health_sciences \
  --seed-mode doi \
  --doi 10.1056/NEJMoa2031054 \
  --output-dir presentacion/prueba2 \
  --verbose
```

---

### 🔄 2. Regenerating R Assets After Manual Excel Edits — Lightweight Mode

If you manually edit or clean up rows (such as correcting author names, title typos, or manual evidence grades) in the compiled Excel matrix (`matriz_auditoria_automatizada.xlsx`), you **must** update the R visualizations and report files to keep them consistent. 

Instead of re-running the entire API download pipeline, you can run these lightweight commands to rebuild the R assets directly from your edited Excel file:

#### Step 1: Update the Native R Keywords Network & Markdown Summary
Reads the edited Excel file to generate `red_coocurrencia.html` and `base_bibliometria.md`:
```bash
python -m bibliometric_analyzer.cli --r-native \
  --input "presentacion/prueba/matriz_auditoria_automatizada.xlsx" \
  --output-html "presentacion/prueba/red_coocurrencia.html" \
  --output-md "presentacion/prueba/base_bibliometria.md"
```

#### Step 2: Update the R Markdown Editorial HTML Report
Reads the edited Excel file to compile `reporte_editorial.html`:
```bash
python -m bibliometric_analyzer.cli --r-report \
  --input "presentacion/prueba/matriz_auditoria_automatizada.xlsx" \
  --output-html "presentacion/prueba/reporte_editorial.html" \
  --theme "phytochemistry"
```

---

### 🌳 3. Standalone Citation Lineage Crawling (`--linaje`)

If you only need to build a citation lineage network (ancestors and descendants) and export it to an interactive 2D graph and Markdown file, use:
```bash
python -m bibliometric_analyzer.cli --linaje \
  --doi 10.1007/s00726-025-03491-0 \
  --theme phytochemistry \
  --api-source all \
  --max-refs 20 \
  --depth 1 \
  --output-html red_investigacion.html \
  --output-md base_conocimiento.md
```

---

### 📋 4. Blank Excel Matrix Generation (`--generate-matrix`)

Generates a blank systematic review Excel template populated with premium styles, formulas, and theme-specific columns (including Grade, Cochrane Risk of Bias, and sample data):
```bash
python -m bibliometric_analyzer.cli --generate-matrix \
  --theme health_sciences \
  --output plantilla_salud.xlsx
```

---

### 📐 5. Interactive PRISMA 2020 Flow Generator (`--prisma-flow`)

Launches an interactive wizard in the terminal to walk you through the PRISMA 2020 inclusion/exclusion screening counts and compiles a `.mermaid` flowchart:
```bash
python -m bibliometric_analyzer.cli --prisma-flow \
  --output prisma.mermaid
```

---

## API Caching System

To comply with API limits and allow instant re-runs, the tool implements a **Local JSON Cache** located by default at:
`~/.bibliometric_cache/`

- Subsequent requests with the same DOI or query will serve directly from the disk cache.
- To purge the cache and force new queries to live API servers, use the `--clear-cache` flag:
```bash
python -m bibliometric_analyzer.cli --clear-cache
```

---

## Complete CLI Reference

| Argument | Type | Default | Description |
|---|---|---|---|
| `--pipeline` | Flag | `False` | **Executes the full E2E automated 5-stage research pipeline.** |
| `--linaje` | Flag | `False` | Runs citation lineage tracking for a specific seed DOI. |
| `--theme` | Choice | `general` | Discipline column/extraction schema: `phytochemistry`, `health_sciences`, `industrial_engineering`, `computer_science`, `general`. |
| `--seed-mode` | Choice | `search` | Seed selector: `doi` (direct DOI input) or `search` (auto query search). |
| `--doi` | String | `None` | Seed DOI for lineage engine crawling. |
| `--search-query` | String | `None` | Search topic query for automatic seed selection. |
| `--output-dir` | Path | `None` | Output directory where all generated files will be written. |
| `--api-source` | Choice | `all` | API cascade selection: `all`, `scopus`, `pubmed`, or `openalex`. |
| `--max-refs` | Int | `12` | Maximum ancestor references crawled per node. |
| `--depth` | Int | `1` | Recursive BFS search depth. |
| `--generate-matrix`| Flag | `False` | Generates a blank theme-specific Excel review template. |
| `--prisma-flow` | Flag | `False` | Launches the terminal interactive PRISMA wizard. |
| `--check-r` | Flag | `False` | Verifies R environment and automatically installs packages. |
| `--r-native` | Flag | `False` | Runs native R co-occurrence analysis on an input Excel. |
| `--r-report` | Flag | `False` | Compiles an R Markdown editorial HTML report from an input Excel. |
| `--input` | Path | `None` | Input Excel file path for `--r-native` or `--r-report` tasks. |
| `--output-html` | Path | `None` | Output HTML path for R report or Vis.js graphs. |
| `--output-md` | Path | `None` | Output Markdown path for lineage metadata. |
| `--clear-cache` | Flag | `False` | Purges all cached JSON responses from the local directory. |
| `--verbose` | Flag | `False` | Enables detailed logging to the terminal. |

---

## Package Architecture

```
src/bibliometric_analyzer/
├── __init__.py         # Package metadata
├── cli.py              # CLI entrypoint and argument validation
├── utils.py            # Logger, JSONCache, SSL contexts, compound author parser
├── scopus_client.py    # Elsevier Scopus API connector
├── openalex_client.py  # OpenAlex REST API connector
├── pubmed_client.py    # NCBI Entrez client
├── lineage_engine.py   # BFS crawler, PageRank algorithm, qualitative extractors
├── visualizer.py       # Vis.js network builder (interactive HTML)
├── r_bridge.py         # Rscript compiler, Pandoc configs, fallback Python Plotly generator
├── matrix_generator.py # Excel sheet creator and quality score handlers
└── themes.py           # Domain schemas (phytochemistry, health_sciences, etc.)
```

---

## Running Unit Tests

Run the test suite using `pytest` or `unittest`:
```bash
python -m pytest
```

---

## License

MIT License — see [LICENSE](LICENSE).
