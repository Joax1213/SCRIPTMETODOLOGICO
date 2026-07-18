import os
import re
import time
import urllib.request
import json
import ssl
import logging
from collections import deque
import pandas as pd
import networkx as nx

from .utils import parse_author_name, format_authors_list, get_fallback_year, get_ssl_context
from .scopus_client import get_scopus_paper_data, get_scopus_abstract, get_citing_papers_scopus
from .openalex_client import get_openalex_paper_data, get_citing_papers_openalex, rebuild_abstract_inverted_index
from .pubmed_client import get_pubmed_paper_data, get_citing_papers_pubmed
from .themes import get_theme, generate_qualitative_for_theme

logger = logging.getLogger("bibliometric_analyzer")

def download_pdf(url, dest_path, verbose=False, verify_ssl=True):
    ctx = get_ssl_context(verify_ssl)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            with open(dest_path, "wb") as f:
                f.write(response.read())
        logger.debug(f"[PDF Downloader] Descarga exitosa de: {url}")
        return True
    except Exception as e:
        logger.debug(f"[PDF Downloader] Error al descargar PDF desde {url}: {e}")
        return False

def extract_text_from_pdf(pdf_path):
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text.strip()
    except Exception as e:
        logger.warning(f"Error al extraer texto de {pdf_path}: {e}")
        return ""

def index_local_pdfs(pdf_dir, verbose=False):
    pdf_mapping = {}
    if not pdf_dir or not os.path.exists(pdf_dir):
        return pdf_mapping

    logger.info(f"[Indexador PDF] Escaneando directorio local: {pdf_dir}")
    for root_dir, _, files in os.walk(pdf_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(root_dir, file)
                text_sample = ""
                try:
                    import pypdf
                    reader = pypdf.PdfReader(pdf_path)
                    pages_to_read = min(len(reader.pages), 3)
                    for i in range(pages_to_read):
                         extracted = reader.pages[i].extract_text()
                         if extracted:
                              text_sample += extracted + "\n"
                except Exception:
                    pass

                doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", text_sample)
                if doi_match:
                    doi = doi_match.group(0).strip().strip(".").strip("/")
                    pdf_mapping[doi.lower()] = pdf_path
                    logger.debug(f"  - Indexado por DOI: {file} -> {doi}")
                else:
                    title_clean = re.sub(r'[^a-z0-9]', '', file.lower().replace(".pdf", ""))
                    pdf_mapping[title_clean] = pdf_path
                    logger.debug(f"  - Indexado por nombre de archivo: {file} -> {title_clean[:30]}...")
    return pdf_mapping

def get_unpaywall_pdf_url(doi, contact_email, verbose=False, verify_ssl=True):
    clean_doi = doi.replace("https://doi.org/", "").strip()
    email_param = contact_email if contact_email else "user@example.com"
    url = f"https://api.unpaywall.org/v2/{clean_doi}?email={email_param}"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = get_ssl_context(verify_ssl)

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("is_oa", False):
                    best_oa = data.get("best_oa_location") or {}
                    pdf_url = best_oa.get("url_for_pdf")
                    if pdf_url:
                        return pdf_url
                    for loc in data.get("oa_locations", []):
                        if loc and loc.get("url_for_pdf"):
                            return loc.get("url_for_pdf")
    except Exception as e:
        logger.debug(f"[Unpaywall API] Error al consultar para DOI {doi}: {e}")
    return None

def generate_heuristic_qualitative_data(title, abstract, full_text=None, theme="general"):
    """Genera descubrimientos y aportes cualitativos usando la lógica del tema seleccionado."""
    text_to_analyze = full_text if (full_text and len(full_text) > len(abstract)) else abstract
    return generate_qualitative_for_theme(theme, title, text_to_analyze)

def get_paper_metadata_unified(doi, api_source, scopus_key, pubmed_key, contact_email, cache=None, verify_ssl=True):
    clean_doi = doi.replace("https://doi.org/", "").strip().lower()
    
    if cache:
        cached = cache.get("metadata", clean_doi)
        if cached:
            return cached

    payload = None
    source_api = "None"
    
    if api_source in ["scopus", "all"] and scopus_key:
        logger.debug(f"[Lineage] Intentando recuperar {clean_doi} en Scopus...")
        scopus_data = get_scopus_paper_data(clean_doi, scopus_key, verify_ssl=verify_ssl)
        if scopus_data:
            title = scopus_data.get("dc:title", "Sin título")
            cover_date = scopus_data.get("prism:coverDate", "")
            year = cover_date.split("-")[0] if "-" in cover_date else str(get_fallback_year())
            journal = scopus_data.get("prism:publicationName", "N/A")
            
            creator = scopus_data.get("dc:creator", "Desconocido")
            author = parse_author_name(creator)
            
            eid = scopus_data.get("eid")
            abstract = get_scopus_abstract(eid, scopus_key, verify_ssl=verify_ssl) if eid else None
            
            payload = {
                "DOI": clean_doi,
                "Título": title,
                "Autores": author,
                "Año": year,
                "Revista": journal,
                "Abstract": abstract,
                "raw_api": "scopus",
                "referenced_works": []
            }
            source_api = "scopus"

    if not payload and api_source in ["pubmed", "all"]:
        logger.debug(f"[Lineage] Intentando recuperar {clean_doi} en PubMed...")
        pubmed_data = get_pubmed_paper_data(clean_doi, pubmed_key, verify_ssl=verify_ssl)
        if pubmed_data:
            payload = {
                "DOI": pubmed_data["DOI"],
                "Título": pubmed_data["Título"],
                "Autores": pubmed_data["Autores"],
                "Año": pubmed_data["Año"],
                "Revista": pubmed_data["Revista"],
                "Abstract": pubmed_data["Abstract"],
                "raw_api": "pubmed",
                "referenced_works": []
            }
            source_api = "pubmed"

    if not payload and api_source in ["openalex", "all"]:
        logger.debug(f"[Lineage] Intentando recuperar {clean_doi} en OpenAlex...")
        alex_data = get_openalex_paper_data(clean_doi, contact_email, verify_ssl=verify_ssl)
        if alex_data:
            title = alex_data.get("title", "Sin título")
            year = str(alex_data.get("publication_year", get_fallback_year()))
            
            authorships = alex_data.get("authorships", [])
            authors_list = [a.get("author", {}).get("display_name", "") for a in authorships]
            author = format_authors_list(authors_list)
            
            primary_loc = alex_data.get("primary_location") or {}
            source = (primary_loc.get("source") or {}) if isinstance(primary_loc, dict) else {}
            journal = source.get("display_name", "N/A") if isinstance(source, dict) else "N/A"
            
            abstract = rebuild_abstract_inverted_index(alex_data.get("abstract_inverted_index")) if "abstract_inverted_index" in alex_data else alex_data.get("abstract", "Abstract no disponible.")
            referenced_works = alex_data.get("referenced_works", [])
            
            payload = {
                "DOI": clean_doi,
                "Título": title,
                "Autores": author,
                "Año": year,
                "Revista": journal,
                "Abstract": abstract,
                "raw_api": "openalex",
                "referenced_works": referenced_works,
                "raw_openalex_json": alex_data
            }
            source_api = "openalex"

    if payload:
        if not payload.get("Abstract") or "Abstract no disponible" in payload.get("Abstract"):
            logger.debug(f"[Lineage] Cruzando abstract vacío de {clean_doi} con OpenAlex...")
            alex_fallback = get_openalex_paper_data(clean_doi, contact_email, verify_ssl=verify_ssl)
            if alex_fallback:
                abs_val = rebuild_abstract_inverted_index(alex_fallback.get("abstract_inverted_index")) if "abstract_inverted_index" in alex_fallback else alex_fallback.get("abstract")
                if abs_val:
                    payload["Abstract"] = abs_val
                if not payload["referenced_works"]:
                    payload["referenced_works"] = alex_fallback.get("referenced_works", [])
                if source_api != "openalex":
                    payload["raw_openalex_json"] = alex_fallback

        if not payload.get("Abstract"):
            payload["Abstract"] = "Abstract no disponible."
            
        if cache:
            cache.set("metadata", clean_doi, payload)
            
        return payload
        
    return None

def validate_paper_criteria(title, abstract, year, full_text=None, start_year=None, end_year=None, precursor_filter=False, precursor_keywords=None):
    """Valida los artículos según año y filtros dinámicos de precursor de la disciplina."""
    if start_year is not None or end_year is not None:
        try:
            y = int(year)
            if start_year is not None and y < start_year:
                logger.debug(f"[Filtro Año] {year} < {start_year}. Descartado.")
                return False
            if end_year is not None and y > end_year:
                logger.debug(f"[Filtro Año] {year} > {end_year}. Descartado.")
                return False
        except (ValueError, TypeError):
            logger.debug(f"[Filtro Año] Año inválido '{year}'. Descartado.")
            return False

    if precursor_filter and precursor_keywords:
        text = f"{title} {abstract or ''} {full_text or ''}".lower()
        has_precursor = any(pk.lower() in text for pk in precursor_keywords)
        
        has_concentration = (
            "concentration" in text or 
            "concentración" in text or 
            "concentraciones" in text or
            " mm" in text or 
            " mg/l" in text or 
            " g/l" in text or 
            " µm" in text or 
            " ug/g" in text or 
            " mg/g" in text or
            " ppm" in text or
            " mmol" in text
        )
        
        if not (has_precursor and has_concentration):
            logger.debug(f"[Filtro Precursor] Falta mención de precursor/concentración en texto. Descartado.")
            return False

    return True

def execute_live_lineage(doi, output_html, output_md, api_source="all", scopus_key="", pubmed_key="", contact_email="",
                         verbose=False, full_text=False, pdf_dir=None, theme="general", max_refs=12, depth=1, cache=None, verify_ssl=True, max_total_nodes=150,
                         start_year=None, end_year=None, precursor_filter=False):
    logger.info(f"[Linaje] Iniciando rastreo para DOI semilla: {doi} (Profundidad: {depth}, Max Refs: {max_refs}, Tema: {theme})")
    
    theme_spec = get_theme(theme)
    precursor_keywords = theme_spec.get("precursor_keywords", [])
    bfs_filter_keywords = theme_spec.get("bfs_filter_keywords", [])

    local_pdfs = index_local_pdfs(pdf_dir, verbose=verbose) if pdf_dir else {}
    documentos_temporales_dir = "documentos_temporales"
    if full_text:
        os.makedirs(documentos_temporales_dir, exist_ok=True)
        logger.info(f"[Texto Completo] Carpeta para descargas temporales: {os.path.abspath(documentos_temporales_dir)}")

    nodes = {}
    edges = []
    failed_nodes = []
    
    queue = deque([(doi.strip().lower(), 0, "Semilla")])
    processed_dois = set()

    def process_paper_qualitative(title, abstract, doi_val, alex_work_json=None):
        clean_doi = doi_val.replace("https://doi.org/", "").strip().lower()
        title_clean = re.sub(r'[^a-z0-9]', '', title.lower())
        
        pdf_path = local_pdfs.get(clean_doi) or local_pdfs.get(title_clean)
        extracted_text = None
        source_type = "Solo abstract"
        
        if pdf_path:
            logger.info(f"      [+] PDF local encontrado: {pdf_path}")
            extracted_text = extract_text_from_pdf(pdf_path)
            if extracted_text:
                source_type = "PDF local indexado"
                
        if not extracted_text and full_text:
            pdf_url = None
            if alex_work_json:
                best_loc = alex_work_json.get("best_oa_location") or {}
                pdf_url = best_loc.get("pdf_url")
                if not pdf_url:
                    for loc in alex_work_json.get("oa_locations", []):
                        if loc and loc.get("pdf_url"):
                            pdf_url = loc.get("pdf_url")
                            break
                            
            safe_doi = re.sub(r'[^a-zA-Z0-9]', '_', clean_doi)
            dest_path = os.path.join(documentos_temporales_dir, f"{safe_doi}.pdf")
            success = False
            
            if pdf_url:
                logger.info(f"      [~] Descargando texto completo OA desde: {pdf_url}")
                success = download_pdf(pdf_url, dest_path, verbose=verbose, verify_ssl=verify_ssl)
                
            if not success:
                logger.debug(f"      [~] Intentando fallback con Unpaywall API...")
                unpaywall_url = get_unpaywall_pdf_url(clean_doi, contact_email, verbose=verbose, verify_ssl=verify_ssl)
                if unpaywall_url:
                    logger.info(f"      [~] Descargando desde Unpaywall: {unpaywall_url}")
                    success = download_pdf(unpaywall_url, dest_path, verbose=verbose, verify_ssl=verify_ssl)
                    
            if success:
                extracted_text = extract_text_from_pdf(dest_path)
                if extracted_text:
                    source_type = "Texto completo descargado"
                    
        desc, app = generate_heuristic_qualitative_data(title, abstract, full_text=extracted_text, theme=theme)
        return desc, app, source_type, extracted_text

    while queue:
        curr_doi, curr_level, pilar = queue.popleft()
        
        if len(processed_dois) >= max_total_nodes:
            logger.warning(f"[Linaje] Se ha alcanzado el límite máximo de nodos totales ({max_total_nodes}). Deteniendo la expansión del grafo.")
            break
        
        if curr_doi in processed_dois:
            continue
        processed_dois.add(curr_doi)
        
        logger.info(f"\n[Linaje] Procesando [{curr_doi}] Nivel {curr_level} ({pilar})...")
        
        paper_data = get_paper_metadata_unified(curr_doi, api_source, scopus_key, pubmed_key, contact_email, cache, verify_ssl=verify_ssl)
        if not paper_data:
            logger.warning(f"[-] No se pudieron obtener metadatos para DOI/ID: {curr_doi}")
            failed_nodes.append({
                "DOI": curr_doi,
                "Nivel": curr_level,
                "Pilar": pilar,
                "Razón": "Metadatos no encontrados en ninguna API habilitada."
            })
            continue

        title = paper_data["Título"]
        abstract = paper_data["Abstract"]
        authors = paper_data["Autores"]
        year = paper_data["Año"]
        journal = paper_data["Revista"]
        referenced_works = paper_data["referenced_works"]
        alex_json = paper_data.get("raw_openalex_json")
        
        desc, app, src_type, text_extracted = process_paper_qualitative(title, abstract, curr_doi, alex_json)
        
        is_seed = (curr_level == 0)
        current_precursor_filter = precursor_filter
        
        if not is_seed and bfs_filter_keywords:
            text_lower = f"{title} {abstract or ''} {text_extracted or ''}".lower()
            if not any(w.lower() in text_lower for w in bfs_filter_keywords):
                logger.info(f"   [-] Artículo [{curr_doi}] ({year}) excluido por no coincidir con palabras clave del tema '{theme}'.")
                failed_nodes.append({
                    "DOI": curr_doi,
                    "Nivel": curr_level,
                    "Pilar": pilar,
                    "Razón": f"Excluido por filtro temático de disciplina (Nivel > 0)."
                })
                continue

        if not validate_paper_criteria(title, abstract, year, text_extracted, start_year, end_year, current_precursor_filter, precursor_keywords):
            logger.info(f"   [-] Artículo [{curr_doi}] ({year}) excluido por criterios de filtrado dinámico (Año/Precursor).")
            failed_nodes.append({
                "DOI": curr_doi,
                "Nivel": curr_level,
                "Pilar": pilar,
                "Razón": f"Excluido por filtro: Año {year} (Rango: {start_year}-{end_year}) o precursor faltante."
            })
            continue
            
        nodes[curr_doi] = {
            "ID": curr_doi,
            "Título": title,
            "Autores": authors,
            "Año": year,
            "Revista": journal,
            "Abstract": abstract,
            "TextoCompleto": text_extracted,
            "Descubrimientos Principales": desc,
            "Aporte al Tema": app,
            "FuenteAnalisis": src_type,
            "EsSemilla": (curr_doi.lower() == doi.strip().lower()),
            "Pilar": pilar,
            "Nivel": curr_level
        }
        
        if curr_level >= depth:
            continue
            
        logger.info(f"  [Ancestros] Obteniendo referencias para {curr_doi}...")
        if not referenced_works and api_source in ["openalex", "all"]:
            alex_json = get_openalex_paper_data(curr_doi, contact_email, verify_ssl=verify_ssl)
            if alex_json:
                referenced_works = alex_json.get("referenced_works", [])
                
        actual_max_refs = len(referenced_works)
        if max_refs is not None:
            actual_max_refs = min(len(referenced_works), max_refs)
            
        logger.info(f"  - Analizando referencias [{actual_max_refs} de {len(referenced_works)} disponibles]")
        
        for idx, ref_openalex_id in enumerate(referenced_works[:actual_max_refs]):
            ref_doi = ref_openalex_id.split("/")[-1]
            ref_data = get_paper_metadata_unified(ref_doi, api_source, scopus_key, pubmed_key, contact_email, cache, verify_ssl=verify_ssl)
            if ref_data:
                ref_clean_doi = ref_data["DOI"]
                edges.append((curr_doi, ref_clean_doi, "Cita a"))
                queue.append((ref_clean_doi, curr_level + 1, "Ancestros"))
            else:
                logger.warning(f"  [-] Fallo al obtener metadatos de referencia: {ref_openalex_id}")
                failed_nodes.append({
                    "DOI": ref_doi,
                    "Nivel": curr_level + 1,
                    "Pilar": "Ancestros",
                    "Razón": f"Referencia citada por {curr_doi} falló al ser recuperada."
                })
            time.sleep(0.1)

        logger.info(f"  [Descendientes] Obteniendo citantes para {curr_doi}...")
        citing_papers = []
        
        if api_source in ["scopus", "all"] and scopus_key:
            citing_papers = get_citing_papers_scopus(curr_doi, title, scopus_key, verbose=verbose, verify_ssl=verify_ssl)
        if not citing_papers and api_source in ["pubmed", "all"]:
            citing_papers = get_citing_papers_pubmed(curr_doi, pubmed_key, count=20, verify_ssl=verify_ssl)
        if not citing_papers and api_source in ["openalex", "all"]:
            citing_papers = get_citing_papers_openalex(curr_doi, contact_email, count=20, verify_ssl=verify_ssl)
            
        logger.info(f"  - Encontrados {len(citing_papers)} citantes.")
        
        for cp in citing_papers:
            cp_doi = cp["DOI"].lower()
            edges.append((cp_doi, curr_doi, "Cita a"))
            queue.append((cp_doi, curr_level + 1, "Descendientes"))
            
    valid_edges = []
    for source, target, rel in edges:
        if source in nodes and target in nodes:
            valid_edges.append((source, target, rel))
            
    logger.info(f"\n[Grafo] Construcción completada: {len(nodes)} nodos, {len(valid_edges)} conexiones filtradas.")
    
    G = nx.DiGraph()
    G.add_nodes_from(nodes.keys())
    for source, target, rel in valid_edges:
        G.add_edge(source, target)
        
    pagerank_scores = nx.pagerank(G, alpha=0.85) if len(G) > 1 else {n: 1.0 for n in G.nodes()}
    degree_centrality = nx.degree_centrality(G)
    
    for node_id, score in pagerank_scores.items():
        if node_id in nodes:
            nodes[node_id]["PageRank"] = score
            nodes[node_id]["Centrality"] = degree_centrality[node_id]

    if output_md:
        write_markdown_knowledge_base_unified(nodes, valid_edges, G, failed_nodes, output_md)
        
    if output_html:
        from .visualizer import write_html_network_visualization
        write_html_network_visualization(nodes, valid_edges, output_html, verify_ssl=verify_ssl, theme_name=theme)
        
    return nodes, valid_edges

def write_markdown_knowledge_base_unified(nodes, edges, G, failed_nodes, path):
    logger.info(f"[Markdown] Compilando reporte en: {path}")
    
    nodos_totales = len(G)
    conexiones_totales = G.number_of_edges()
    densidad = nx.density(G)
    
    try:
        undirected_G = G.to_undirected()
        coef_agrupamiento = nx.average_clustering(undirected_G)
    except Exception:
        coef_agrupamiento = 0.0
        
    top_authorities = sorted(nodes.values(), key=lambda x: x.get("PageRank", 0), reverse=True)[:10]
    
    md = []
    md.append("# Base de Conocimiento del Linaje Científico")
    md.append(f"*Generado el:* {time.strftime('%Y-%m-%d')}  ")
    md.append(f"*Muestra:* {nodos_totales} artículos analizados con éxito  \n")
    
    md.append("## 1. Ficha del Grafo (Métricas de Red)")
    md.append(f"*   **Nodos totales con éxito:** {nodos_totales}")
    md.append(f"*   **Conexiones totales:** {conexiones_totales}")
    md.append(f"*   **Densidad de la red:** {densidad:.4f}")
    md.append(f"*   **Coeficiente de agrupamiento:** {coef_agrupamiento:.4f}")
    md.append("\n*   **Top 10 de Autoridades Científicas (PageRank & Centralidad):**")
    
    for idx, auth in enumerate(top_authorities):
        autores_corto = auth['Autores'].split(',')[0] if ',' in auth['Autores'] else auth['Autores']
        md.append(f"    {idx+1}. **{autores_corto} ({auth['Año']})** - PageRank: {auth.get('PageRank', 0):.4f} - Centralidad: {auth.get('Centrality', 0):.4f} · *{auth['Revista']}*")
    
    md.append("\n## 2. Reporte de Incidentes de Extracción")
    if failed_nodes:
        md.append(f"Se registraron **{len(failed_nodes)}** incidentes de red o inconsistencias de datos al armar el linaje:")
        md.append("| DOI / ID | Pilar original | Nivel | Razón del Incidente |")
        md.append("|---|---|---|---|")
        for fn in failed_nodes:
            md.append(f"| `{fn['DOI']}` | {fn['Pilar']} | {fn['Nivel']} | {fn['Razón']} |")
    else:
        md.append("¡Extracción completada sin incidentes de red ni fallos de datos!")
        
    md.append("\n---\n")
    md.append("## 3. Mapa de Conexiones Dirigidas (El Linaje de Citas)")
    
    for n_id, n_data in nodes.items():
        citation_key = f"{n_data['Autores'].split(',')[0] if ',' in n_data['Autores'] else n_data['Autores']} ({n_data['Año']})"
        md.append(f"### [{n_id}] {citation_key} · *{n_data['Revista']}*")
        md.append(f"*   **Título:** {n_data['Título']}")
        md.append(f"*   **DOI:** [https://doi.org/{n_id}](https://doi.org/{n_id})")
        md.append(f"*   **Método de Análisis:** {n_data['FuenteAnalisis']}")
        md.append(f"*   **Abstract:** {n_data['Abstract']}")
        md.append(f"*   **Descubrimientos Principales:** {n_data['Descubrimientos Principales']}")
        md.append(f"*   **Aporte al Tema:** {n_data['Aporte al Tema']}")
        
        ancestros = [target for source, target in G.edges() if source == n_id]
        md.append("*   **Ancestros Directos (A quién cita):**")
        if ancestros:
            for anc in ancestros:
                anc_data = nodes.get(anc)
                if anc_data:
                    anc_key = f"{anc_data['Autores'].split(',')[0] if ',' in anc_data['Autores'] else anc_data['Autores']} ({anc_data['Año']})"
                    md.append(f"    - [{anc}](https://doi.org/{anc}) {anc_key}")
                else:
                    md.append(f"    - [{anc}](https://doi.org/{anc}) DOI Externo")
        else:
            md.append("    - *Ninguno identificado en el grafo local*")
            
        descendientes = [source for source, target in G.edges() if target == n_id]
        md.append("*   **Descendientes Directos (Quién lo cita):**")
        if descendientes:
            for desc in descendientes:
                desc_data = nodes.get(desc)
                if desc_data:
                    desc_key = f"{desc_data['Autores'].split(',')[0] if ',' in desc_data['Autores'] else desc_data['Autores']} ({desc_data['Año']})"
                    md.append(f"    - [{desc}](https://doi.org/{desc}) {desc_key}")
                else:
                    md.append(f"    - [{desc}](https://doi.org/{desc}) DOI Externo")
        else:
            md.append("    - *Ninguno identificado en el grafo local*")
        md.append("")
        
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        logger.info("[Markdown] Reporte compilado con éxito.")
    except Exception as e:
        logger.error(f"Error al escribir reporte Markdown: {e}")
