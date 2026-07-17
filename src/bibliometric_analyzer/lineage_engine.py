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

logger = logging.getLogger("bibliometric_analyzer")

def download_pdf(url, dest_path, verbose=False, verify_ssl=True):
    """Descarga un PDF desde una URL y lo guarda localmente."""
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
    """Extrae texto plano de un archivo PDF usando pypdf."""
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
    """Escanea un directorio local e indexa archivos PDF por su DOI detectado o por título."""
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
    """Busca una versión legal en acceso abierto para un DOI usando la API de Unpaywall."""
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
    """Genera descripciones heurísticas sobre descubrimientos y aportes al tema."""
    text_to_analyze = full_text if (full_text and len(full_text) > len(abstract)) else abstract

    if not text_to_analyze or "Abstract no disponible" in text_to_analyze or len(text_to_analyze) < 30:
        return (
            "Investigación sobre bioprocesos, regeneración o biomoléculas en biotecnología.",
            "Respaldo directo de la literatura científica para el marco teórico de la investigación."
        )

    discoveries = ""
    aporte = ""

    if theme == "phytochemistry":
        yield_matches = re.findall(r"(?:\d+(?:\.\d+)?)\s*(?:mg/g|ug/g|g/kg|mg/L|mg\s+g\s*-1)", text_to_analyze, re.IGNORECASE)
        hplc_matches = re.findall(r"(?:HPLC|cromatografía|chromatography|LC-MS|GC-MS|spectrophotometr\w*)", text_to_analyze, re.IGNORECASE)
        elicitor_matches = re.findall(r"(?:elicitor|elicitation|tyrosine|tirosina|methyl jasmonate|salicylic acid|chitosan|yeast extract|precursor)", text_to_analyze, re.IGNORECASE)

        desc_parts = []
        if yield_matches:
            unique_yields = list(dict.fromkeys(yield_matches))[:2]
            desc_parts.append(f"Reporta rendimientos cuantitativos de metabolitos en rangos de {', '.join(unique_yields)}.")
        if hplc_matches:
            unique_tech = list(dict.fromkeys([t.upper() for t in hplc_matches]))[:2]
            desc_parts.append(f"Valida el perfil fitoquímico mediante técnicas instrumentales: {', '.join(unique_tech)}.")
        if elicitor_matches:
            unique_el = list(dict.fromkeys([e.lower() for e in elicitor_matches]))[:2]
            desc_parts.append(f"Estudia el efecto fisiológico de inductores y precursores: {', '.join(unique_el)}.")

        if desc_parts:
            discoveries = " ".join(desc_parts)
        else:
            sentences = re.split(r'\. (?=[A-Z])', text_to_analyze)
            for sent in sentences:
                if any(w in sent.lower() for w in ["showed", "demonstrated", "results", "found", "concluded", "revealed", "yield", "hplc"]):
                    discoveries = sent.strip()
                    break

        if not discoveries:
            discoveries = "Análisis fitoquímico y de inducción de metabolitos secundarios en tejido vegetal."

        title_lower = title.lower()
        if "vicia" in title_lower or "faba" in title_lower or "haba" in title_lower or "broad bean" in title_lower:
            aporte = "Aporta parámetros clave para optimizar la biosíntesis de L-DOPA y regular la respuesta de polifenol oxidasas (PPO) en leguminosas."
        elif yield_matches:
            aporte = "Proporciona bases experimentales de rendimiento de metabolitos para el escalamiento de procesos de elicitación vegetal."
        else:
            aporte = "Aporta a la optimización operacional y fisiológica de la biosíntesis de compuestos bioactivos en modelos vegetales."

    else:
        # Tema General
        sentences = []
        if full_text and len(full_text) > 3000:
            conclusions_chunk = full_text[-2500:]
            sentences = re.split(r'\. (?=[A-Z])', conclusions_chunk)
        else:
            sentences = re.split(r'\. (?=[A-Z])', text_to_analyze)

        for sent in sentences:
            if any(w in sent.lower() for w in ["conclude", "conclusion", "overall", "therefore", "summary", "suggest", "indicates", "demonstrate"]):
                clean_sent = sent.strip()
                if 30 < len(clean_sent) < 200:
                    discoveries = clean_sent
                    if not discoveries.endswith("."):
                        discoveries += "."
                    break

        if not discoveries:
            for sent in re.split(r'\. (?=[A-Z])', text_to_analyze):
                if any(w in sent.lower() for w in ["showed", "demonstrated", "results", "found", "revealed", "we report"]):
                    discoveries = sent.strip()
                    if not discoveries.endswith("."):
                        discoveries += "."
                    break

        if not discoveries:
            discoveries = f"Estudio enfocado en el análisis, caracterización y modelado de {title.lower()}."

        title_lower = title.lower()
        if any(w in title_lower for w in ["bioreactor", "culture", "bioprocess", "production", "titer", "yield", "fermentation", "media"]):
            aporte = "Proporciona parámetros y metodologías críticas para la optimización de bioprocesos y rendimiento en biorreactores."
        elif any(w in title_lower for w in ["vector", "lentiviral", "gene", "transduction", "delivery", "transfection", "plasmid"]):
            aporte = "Aporta bases para el diseño y optimización de vectores y sistemas de transferencia génica a nivel celular."
        elif any(w in title_lower for w in ["stem cell", "differentiation", "regeneration", "tissue", "cell therapy", "pluripotent", "organoid"]):
            aporte = "Sustenta las aplicaciones de terapia celular y regeneración de tejidos basadas en diferenciación celular."
        else:
            aporte = "Aporta evidencia experimental y teórica sobre los mecanismos moleculares y biotecnológicos analizados."

    return discoveries, aporte

def get_paper_metadata_unified(doi, api_source, scopus_key, pubmed_key, contact_email, cache=None, verify_ssl=True):
    """
    Intenta recuperar metadatos consolidados de un DOI usando las APIs habilitadas
    en orden de disponibilidad, leyendo/escribiendo de la caché.
    """
    clean_doi = doi.replace("https://doi.org/", "").strip().lower()
    
    if cache:
        cached = cache.get("metadata", clean_doi)
        if cached:
            return cached

    payload = None
    source_api = "None"
    
    # 1. Intentar Scopus
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
                "referenced_works": [] # Scopus search API no entrega referenced_works directamente de forma simple
            }
            source_api = "scopus"

    # 2. Intentar PubMed
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

    # 3. Fallback a OpenAlex
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
                "raw_openalex_json": alex_data # Guardar datos crudos para descargas
            }
            source_api = "openalex"

    if payload:
        # Completar abstract faltante cruzando con OpenAlex si es posible
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

def validate_paper_criteria(title, abstract, year, full_text=None, start_year=None, end_year=None, precursor_filter=False):
    """Filtra artículos dinámicamente según el rango de años y presencia de precursor con concentraciones."""
    # 1. Validar año
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

    # 2. Validar precursores y concentraciones
    if precursor_filter:
        text = f"{title} {abstract or ''} {full_text or ''}".lower()
        has_precursor = ("tyrosine" in text or "tirosina" in text)
        
        # Buscar términos o abreviaturas asociadas a concentraciones
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
            logger.debug(f"[Filtro Precursor] Falta mención de tirosina o concentración en texto. Descartado.")
            return False

    return True

def execute_live_lineage(doi, output_html, output_md, api_source="all", scopus_key="", pubmed_key="", contact_email="",
                         verbose=False, full_text=False, pdf_dir=None, theme="general", max_refs=12, depth=1, cache=None, verify_ssl=True, max_total_nodes=150,
                         start_year=None, end_year=None, precursor_filter=False):
    """
    Orquesta la construcción del linaje cienciométrico y cualitativo de primer grado o recursivo.
    Soporta opcionalidad de APIs, caché JSON y reporte detallado de incidencias.
    """
    logger.info(f"[Linaje] Iniciando rastreo de linaje para DOI semilla: {doi} (Profundidad: {depth}, Max Refs: {max_refs})")
    
    local_pdfs = index_local_pdfs(pdf_dir, verbose=verbose) if pdf_dir else {}
    documentos_temporales_dir = "documentos_temporales"
    if full_text:
        os.makedirs(documentos_temporales_dir, exist_ok=True)
        logger.info(f"[Texto Completo] Carpeta para descargas temporales: {os.path.abspath(documentos_temporales_dir)}")

    nodes = {}
    edges = []
    failed_nodes = []
    
    # Cola de procesamiento para BFS recursivo: (doi_actual, nivel_actual, pilar_original)
    # pilar_original indica si es "Ancestros", "Descendientes" o "Semilla"
    queue = deque([(doi.strip().lower(), 0, "Semilla")])
    processed_dois = set()

    # Procesar cualitativamente un artículo
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

    # Bucle principal de rastreo
    while queue:
        curr_doi, curr_level, pilar = queue.popleft()
        
        # Control de explosión BFS (techo de nodos totales)
        if len(processed_dois) >= max_total_nodes:
            logger.warning(f"[Linaje] Se ha alcanzado el límite máximo de nodos totales ({max_total_nodes}). Deteniendo la expansión del grafo.")
            break
        
        if curr_doi in processed_dois:
            continue
        processed_dois.add(curr_doi)
        
        logger.info(f"\n[Linaje] Procesando [{curr_doi}] Nivel {curr_level} ({pilar})...")
        
        # Recuperar metadatos unificados
        paper_data = get_paper_metadata_unified(curr_doi, api_source, scopus_key, pubmed_key, contact_email, cache, verify_ssl=verify_ssl)
        if not paper_data:
            logger.warning(f"[-] No se pudieron obtener metadatos para DOI/ID: {curr_doi}")
            failed_nodes.append({
                "DOI": curr_doi,
                "Nivel": curr_level,
                "Pilar": pilar,
                "Razón": "Metadatos no encontrados en ninguna API habilitada o error de conexión."
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
        
        # Validar criterios dinámicos (año y precursores)
        # Para niveles > 0, relajar el filtro de precursor si el usuario lo activó,
        # requiriendo solo que mencione "vicia faba", "dopa", "tyrosine", "tirosina", "legume", "haba"
        # para que la red cienciométrica no se quede con 1 solo nodo
        is_seed = (curr_level == 0)
        current_precursor_filter = precursor_filter
        if not is_seed and precursor_filter:
            current_precursor_filter = False
            text_lower = f"{title} {abstract or ''} {text_extracted or ''}".lower()
            if not any(w in text_lower for w in ["vicia", "faba", "dopa", "tyrosine", "tirosina", "legume", "haba"]):
                logger.info(f"   [-] Artículo [{curr_doi}] ({year}) excluido por no tener palabras clave generales de fitoquímica/haba.")
                failed_nodes.append({
                    "DOI": curr_doi,
                    "Nivel": curr_level,
                    "Pilar": pilar,
                    "Razón": f"Excluido por filtro temático suave (Nivel > 0)."
                })
                continue

        if not validate_paper_criteria(title, abstract, year, text_extracted, start_year, end_year, current_precursor_filter):
            logger.info(f"   [-] Artículo [{curr_doi}] ({year}) excluido por criterios de filtrado dinámico (Año/Precursor).")
            failed_nodes.append({
                "DOI": curr_doi,
                "Nivel": curr_level,
                "Pilar": pilar,
                "Razón": f"Excluido por filtro: Año {year} (Rango: {start_year}-{end_year}) o términos de precursor faltantes."
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
        
        # Detener la expansión si alcanzamos la profundidad límite
        if curr_level >= depth:
            continue
            
        # 1. Expandir referencias (Ancestros) - Citas hacia atrás
        logger.info(f"  [Ancestros] Obteniendo referencias para {curr_doi}...")
        
        # Comprobar si hay referencias disponibles
        if not referenced_works and api_source in ["openalex", "all"]:
            # Si no las tiene cargadas, intentar OpenAlex de forma explícita
            alex_json = get_openalex_paper_data(curr_doi, contact_email, verify_ssl=verify_ssl)
            if alex_json:
                referenced_works = alex_json.get("referenced_works", [])
                
        actual_max_refs = len(referenced_works)
        if max_refs is not None:
            actual_max_refs = min(len(referenced_works), max_refs)
            
        logger.info(f"  - Analizando referencias [{actual_max_refs} de {len(referenced_works)} disponibles]")
        
        for idx, ref_openalex_id in enumerate(referenced_works[:actual_max_refs]):
            # Extraer DOI o ID de OpenAlex
            ref_doi = ref_openalex_id.split("/")[-1]
            # Consultar metadatos para la referencia
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

        # 2. Expandir citantes (Descendientes) - Citas hacia adelante
        logger.info(f"  [Descendientes] Obteniendo citantes para {curr_doi}...")
        citing_papers = []
        
        # Consultar Scopus si está activo
        if api_source in ["scopus", "all"] and scopus_key:
            citing_papers = get_citing_papers_scopus(curr_doi, title, scopus_key, verbose=verbose, verify_ssl=verify_ssl)
            
        # Consultar PubMed si está activo
        if not citing_papers and api_source in ["pubmed", "all"]:
            citing_papers = get_citing_papers_pubmed(curr_doi, pubmed_key, count=20, verify_ssl=verify_ssl)
            
        # Fallback a OpenAlex si no hay resultados previos
        if not citing_papers and api_source in ["openalex", "all"]:
            citing_papers = get_citing_papers_openalex(curr_doi, contact_email, count=20, verify_ssl=verify_ssl)
            
        logger.info(f"  - Encontrados {len(citing_papers)} citantes.")
        
        for cp in citing_papers:
            cp_doi = cp["DOI"].lower()
            edges.append((cp_doi, curr_doi, "Cita a"))
            queue.append((cp_doi, curr_level + 1, "Descendientes"))
            
    # --- MODELADO DE RED ---
    # Filtrar arcos para incluir solo aquellos cuyos extremos existan en el diccionario de nodos válidos
    valid_edges = []
    for source, target, rel in edges:
        if source in nodes and target in nodes:
            valid_edges.append((source, target, rel))
            
    logger.info(f"\n[Grafo] Construcción completada: {len(nodes)} nodos, {len(valid_edges)} conexiones filtradas (de {len(edges)} totales).")
    
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

    # Escribir reportes
    if output_md:
        write_markdown_knowledge_base_unified(nodes, valid_edges, G, failed_nodes, output_md)
        
    if output_html:
        from .visualizer import write_html_network_visualization
        write_html_network_visualization(nodes, valid_edges, output_html, verify_ssl=verify_ssl)
        
    return nodes, valid_edges

def write_markdown_knowledge_base_unified(nodes, edges, G, failed_nodes, path):
    """Genera una base de conocimiento en Markdown que detalla los nodos, conexiones y errores de la red."""
    logger.info(f"[Markdown] Compilando reporte de base de conocimiento en: {path}")
    
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
    
    # Registrar incidentes de red o fallos
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
        
        # Ancestros
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
            
        # Descendientes
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
