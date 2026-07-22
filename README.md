# Bibliometric Analyzer

**Science Lineage & Bibliometrics CLI** — A Python command-line tool for automated bibliometric analysis, live citation lineage mapping, multi-repository extraction, systematic review matrix generation, and R-Bibliometrix integration.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## Overview

`bibliometric-analyzer` is a CLI tool designed for academic researchers to automate end-to-end scientific literature mapping starting from a seed DOI or topic query. It integrates **Scopus Search API**, **PubMed Entrez API**, and **OpenAlex Global API** in an automated cascade to:

- **Map live citation lineage** (ancestors & descendants) using recursive BFS and PageRank centrality ranking.
- **Generate systematic review Excel matrices** populated with Cochrane risk of bias and GRADE evidence rubrics.
- **Produce PRISMA 2020 flow diagrams** (`.mermaid` and PNG exports) tracking study selection.
- **Run automated R-Bibliometrix analysis** and compile formal R Markdown editorial reports (`reporte_editorial.html`).
- **Create standalone interactive 2D network visualizers** (`red_investigacion.html` & `red_coocurrencia.html`) using Vis.js.

---

## Features & Supported Themes

| Theme Code (`--theme`) | Domain / Focus | Key Fields Extracted |
|---|---|---|
| `phytochemistry` | Plant Biochemistry & Bio-processes | Plant Species, Plant Part/Tissue, Elicitor/Precursor, HPLC-UV, Yield (mg/g) |
| `health_sciences` | Medical Genomics & Clinical Trials | Study Type (RCT/Cohort), Sample Size, Intervention, Outcome, OR/HR/$p$-value, GRADE |
| `industrial_engineering` | Process Optimization | Industrial Process, Methodology (Six Sigma/DMAIC), KPI (OEE/Cpk), Improvement % |
| `computer_science` | AI & Software Engineering | Model Architecture, Benchmark Dataset, Metric (F1/Accuracy/Latency), Baseline |
| `general` | Multidisciplinary Studies | General Research Objectives, Methodological Design, Key Findings |

---

## Installation

### 1. Clone & Install Package

```bash
git clone https://github.com/Joax1213/SCRIPTMETODOLOGICO.git
cd SCRIPTMETODOLOGICO
pip install -e .
```

### 2. Manual Dependency Installation

```bash
pip install -r requirements.txt
```

### 3. System Prerequisites (Optional for R Reports)
- **Python 3.8+**
- **R / Rscript 4.0+** (Required for `--r-report` and `--pipeline` R-Bibliometrix integration)
- **Pandoc** (Required for R Markdown HTML report rendering)

---

## Environment Configuration (`.env`)

Create a `.env` file in the root folder or export the following variables:

```dotenv
# Required for OpenAlex (strongly recommended — unlocks polite pool rate limits)
CONTACT_EMAIL=your@email.com

# Optional — Enables Scopus metadata enrichment (requires institutional API key)
SCOPUS_API_KEY=your_scopus_key

# Optional — Increases PubMed API rate limit from 3 to 10 requests/sec
NCBI_API_KEY=your_ncbi_key
```

> **Note:** The tool operates in full open mode using OpenAlex without requiring any API keys.

---

## Usage Guide

### 🚀 1. Complete Automated Research Pipeline (`--pipeline`) — Recommended

The `--pipeline` flag executes the full 5-stage automated research workflow from a seed DOI or topic query to the final R Markdown editorial report:

```bash
# Example A: Phytochemistry Pipeline (Vicia faba / L-DOPA)
python -m bibliometric_analyzer.cli --pipeline \
  --theme phytochemistry \
  --seed-mode doi \
  --doi 10.1002/leg3.129 \
  --output-dir presentacion/prueba \
  --verbose

# Example B: Health Sciences & Clinical Genomics Pipeline (CRISPR-Cas9 NEJM Trial)
python -m bibliometric_analyzer.cli --pipeline \
  --theme health_sciences \
  --seed-mode doi \
  --doi 10.1056/NEJMoa2031054 \
  --output-dir presentacion/prueba2 \
  --verbose
```

#### What `--pipeline` does automatically:
1. **Stage 1 (Seed Selection):** Resolves the seed DOI or performs an automated query search.
2. **Stage 2 (Lineage Crawling):** Executes BFS exploration across Scopus, PubMed, and OpenAlex.
3. **Stage 3 (Matrix & PRISMA Generation):** Populates the Excel systematic review matrix (`matriz_auditoria_automatizada.xlsx`) and PRISMA 2020 flow diagram (`figuras/prisma_flow.png`).
4. **Stage 4 (R-Bibliometrix Integration):** Runs Rscript to extract keyword co-occurrences (`r_keywords.csv`).
5. **Stage 5 (Editorial Report Compilation):** Compiles the R Markdown report into `reporte_editorial.html`.

---

### 2. Standalone Citation Lineage Crawling (`--linaje`)

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

### 3. Generate Blank Audit Matrix Template (`--generate-matrix`)

```bash
python -m bibliometric_analyzer.cli --generate-matrix \
  --theme health_sciences \
  --output plantilla_salud.xlsx
```

---

### 4. Interactive PRISMA Flow Assistant (`--prisma-flow`)

```bash
python -m bibliometric_analyzer.cli --prisma-flow \
  --output prisma.mermaid
```

---

### 5. R Bibliometrics Batch Report (`--r-report`)

```bash
python -m bibliometric_analyzer.cli --r-report \
  --input matriz_auditoria_automatizada.xlsx \
  --output-html reporte_editorial.html
```

---

### 6. Cache Management (`--clear-cache`)

```bash
# Clear local API JSON cache
python -m bibliometric_analyzer.cli --clear-cache

# Specify a custom cache location
python -m bibliometric_analyzer.cli --linaje --doi 10.xxxx/xxxx --cache-dir ./my_cache
```

---

## Complete CLI Arguments Reference

| Argument | Type | Default | Description |
|---|---|---|---|
| `--pipeline` | Flag | `False` | **Executes the full automated 5-stage research pipeline.** |
| `--linaje` | Flag | `False` | Runs citation lineage tracking for a specific DOI. |
| `--theme` | Choice | `general` | Domain schema (`phytochemistry`, `health_sciences`, `industrial_engineering`, `computer_science`). |
| `--seed-mode` | Choice | `search` | Seed input mode: `doi` (user DOI) or `search` (auto query search). |
| `--doi` | String | `None` | Seed DOI for lineage tracking or pipeline Stage 1. |
| `--search-query` | String | `None` | Search topic query for automatic seed selection. |
| `--output-dir` | Path | `None` | Output directory where all generated report files will be written. |
| `--api-source` | Choice | `all` | API source cascade: `all` (Scopus → PubMed → OpenAlex), `scopus`, `pubmed`, or `openalex`. |
| `--max-refs` | Int | `12` | Maximum ancestor references retrieved per node. |
| `--depth` | Int | `1` | Recursive BFS search depth. |
| `--generate-matrix`| Flag | `False` | Generates a blank Excel systematic review template for a theme. |
| `--prisma-flow` | Flag | `False` | Launches the interactive PRISMA 2020 flow wizard. |
| `--r-report` | Flag | `False` | Compiles an R Markdown editorial report from an Excel matrix. |
| `--clear-cache` | Flag | `False` | Clears local API cache files. |
| `--verbose` | Flag | `False` | Enables detailed logging to console. |

---

## Package Architecture

```
src/bibliometric_analyzer/
├── __init__.py         # Package metadata
├── cli.py              # CLI entrypoint and argument parser (--pipeline, --linaje, etc.)
├── utils.py            # Logger, JSONCache, SSL context, author normalization
├── scopus_client.py    # Elsevier Scopus API client
├── openalex_client.py  # OpenAlex API client
├── pubmed_client.py    # NCBI PubMed Entrez API client
├── lineage_engine.py   # BFS crawler, PageRank algorithm, qualitative qualitative synthesis
├── visualizer.py       # Standalone interactive Vis.js HTML network generator
├── r_bridge.py         # Rscript, bibliometrix, and R Markdown integration
├── matrix_generator.py # Excel matrix builder and PRISMA 2020 flow generator
└── themes.py           # Domain schemas (phytochemistry, health_sciences, etc.)
```

---

## Running Unit Tests

```bash
python -m unittest discover -s tests
```

---

## License

MIT License — see [LICENSE](LICENSE).
