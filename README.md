# Bibliometric Analyzer

**Science Lineage & Bibliometrics CLI** — A Python tool for automated bibliometric analysis, citation lineage mapping, and systematic review assistance.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## Overview

`bibliometric-analyzer` is a command-line tool designed for researchers and academics that integrates multiple scientific database APIs to:

- **Map citation lineage** (ancestors and descendants) for any DOI using OpenAlex, Scopus, and PubMed.
- **Generate interactive network visualizations** (Vis.js dual-tab: citation network + concept co-occurrence network).
- **Execute bibliometric batch analysis** via R's `bibliometrix` package and Biblioshiny (no PyBibX dependency).
- **Compile structured systematic review matrices** with GRADE/Cochrane quality rubrics.
- **Generate PRISMA flow diagrams** for systematic reviews.

---

## Features

| Feature | Description |
|---|---|
| Multi-API lineage | OpenAlex (free), Scopus (optional key), PubMed (optional key) |
| Local JSON cache | Avoids repeated API calls across runs |
| Structured error reporting | Failed nodes are logged and reported in the final Markdown output |
| Configurable depth | `--depth N` for recursive multi-hop lineage |
| Configurable max-refs | `--max-refs N` to control ancestor breadth |
| Interactive HTML viewer | Dual Vis.js network (citations + concept co-occurrence) with clickable navigation |
| R bridge | Auto-detects `Rscript` and `pandoc` from system PATH |
| Unit tests | Basic coverage for pure functions (author parsing, cache, heuristics) |

---

## Installation

```bash
git clone https://github.com/joaquin/bibliometric-analyzer.git
cd bibliometric-analyzer
pip install -e .
```

Or install dependencies manually:

```bash
pip install -r requirements.txt
```

---

## Configuration (Credentials)

Create a `.env` file in the project root or set the following environment variables:

```dotenv
# Required for OpenAlex (strongly recommended — improves rate limits)
CONTACT_EMAIL=your@email.com

# Optional — Enables Scopus metadata enrichment (requires institutional subscription)
SCOPUS_API_KEY=your_scopus_key

# Optional — Increases PubMed API rate limit from 3 to 10 requests/second
NCBI_API_KEY=your_ncbi_key
# OR
PUBMED_API_KEY=your_ncbi_key
```

> **Note:** The tool runs fully without any API keys using OpenAlex in free, open mode.

---

## Usage

### 1. Citation Lineage (Core Feature)

```bash
python -m bibliometric_analyzer.cli --linaje --doi 10.1007/s00726-025-03491-0 \
  --output-html red.html \
  --output-md base_conocimiento.md
```

With options:

```bash
python -m bibliometric_analyzer.cli --linaje --doi 10.1007/s00726-025-03491-0 \
  --api-source all \
  --max-refs 20 \
  --depth 1 \
  --theme phytochemistry \
  --full-text \
  --verbose \
  --output-html red.html \
  --output-md base_conocimiento.md
```

### 2. Systematic Review Matrix

```bash
python -m bibliometric_analyzer.cli --generate-matrix --theme phytochemistry --output plantilla.xlsx
```

### 3. PRISMA Flow Diagram

```bash
python -m bibliometric_analyzer.cli --prisma-flow --output prisma.mermaid
```

### 4. Metadata Audit

```bash
python -m bibliometric_analyzer.cli --verify-metadata --doi 10.1007/s00726-025-03491-0
```

### 5. R Bibliometrics Report

```bash
python -m bibliometric_analyzer.cli --r-report --input reporte.xlsx --output-html reporte.html
```

### 6. Cache Management

```bash
# Clear local API cache
python -m bibliometric_analyzer.cli --clear-cache

# Use a custom cache directory
python -m bibliometric_analyzer.cli --linaje --doi 10.xxxx/xxxx --cache-dir ./my_cache
```

---

## API Source Options (`--api-source`)

| Value | Description |
|---|---|
| `openalex` | OpenAlex only (free, no key required) |
| `scopus` | Scopus only (requires `SCOPUS_API_KEY`) |
| `pubmed` | PubMed only (free, optional key for higher rate limits) |
| `all` (default) | All APIs in cascade: Scopus → PubMed → OpenAlex |

---

## Package Structure

```
src/bibliometric_analyzer/
├── __init__.py         # Package metadata
├── cli.py              # CLI entrypoint and argument parsing
├── utils.py            # Logger, JSON cache, author name normalization, year utilities
├── scopus_client.py    # Elsevier Scopus API client (optional)
├── openalex_client.py  # OpenAlex API client (free, no key)
├── pubmed_client.py    # NCBI PubMed Entrez API client (optional key)
├── lineage_engine.py   # Citation graph construction, PageRank, qualitative analysis (max_total_nodes protection)
├── visualizer.py       # Interactive Vis.js HTML network generator
├── r_bridge.py         # R / bibliometrix / R Markdown integration
└── matrix_generator.py # Excel template and PRISMA flow generator
```

---

## Running Tests

```bash
python -m unittest discover -s tests
```

---

## Known Limitations

1. **Lineage depth:** By default (`--depth 1`), only first-degree ancestors and descendants are retrieved. Multi-hop recursion is supported via `--depth N` but exponentially increases API calls.
2. **Ancestor coverage:** `--max-refs` controls the maximum number of references analyzed per node. Set `--max-refs 0` to disable the limit (use with caution on papers with 100+ references).
3. **Scopus forward citations:** Uses `REFDOI` operator for precision. Falls back to `REFTITLE` only when no DOI is available — documented as a known limitation.
4. **Abstract availability:** OpenAlex abstract inverted index covers approximately 60% of papers. For the remainder, abstract will show "Abstract no disponible."

---

## Statement of Need & Comparison

Academic researchers performing systematic literature reviews often struggle to construct citation lineage maps (tracing backward references and forward citations) starting from a core "seed" paper. While existing tools offer excellent individual capabilities, they do not provide a unified, programmatic pipeline for this workflow:

- **bibliometrix (R package)**: The industry standard for scientific mapping. However, it requires a pre-downloaded static export file (e.g., from Scopus or Web of Science) and does not support automated API-based live crawling of citation lineage from a single seed DOI.
- **VOSviewer**: A powerful desktop application for visualizing bibliometric networks. However, it is a GUI-only Java desktop app, making it impossible to integrate into automated command-line scripts or headless Python data pipelines.
- **litstudy**: A Python package for literature analysis, but it does not implement automated BFS/recursive citation lineage tracking (ancestor/descendant discovery) from a seed DOI, nor does it generate standalone interactive dual-network HTML reports.

`bibliometric-analyzer` bridges these gaps by providing a CLI-first, fully automated citation lineage engine. Starting from a single query or DOI, it crawls database APIs in a cascade, populates a systematic review matrix, runs R's `bibliometrix` under the hood, and produces clean HTML reports with interactive visualizations.

### Feature Comparison

| Feature | `bibliometrix` (R) | `VOSviewer` | `litstudy` (Python) | `bibliometric-analyzer` (Ours) |
|---|:---:|:---:|:---:|:---:|
| **Automated Seed Lineage Tracking** | ❌ No | ❌ No | ❌ No | **Yes (Scopus/OpenAlex/PubMed)** |
| **Interactive Standalone HTML Output** | ❌ No (requires Shiny) | ❌ No | ❌ No | **Yes (Vis.js dual-tab)** |
| **Scriptable Python API / CLI** | ❌ No (R only) | ❌ No | Yes | **Yes** |
| **Automated systematic review Excel template** | ❌ No | ❌ No | ❌ No | **Yes (GRADE/phytochemistry)** |
| **PRISMA flow generation** | ❌ No | ❌ No | ❌ No | **Yes (Interactive)** |

---

## License

MIT License — see [LICENSE](LICENSE).
