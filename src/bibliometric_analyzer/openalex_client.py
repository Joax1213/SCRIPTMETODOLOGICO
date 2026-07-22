import html
import re
import urllib.request
import json
import logging
from .utils import format_authors_list, get_ssl_context

logger = logging.getLogger("bibliometric_analyzer")

def _clean_openalex_title(raw_title):
    """Descodifica entidades HTML y elimina etiquetas HTML residuales de los títulos de OpenAlex."""
    if not raw_title:
        return raw_title
    # 1. Desescapar entidades HTML (&lt;i&gt; -> <i>, &amp; -> &, etc.)
    unescaped = html.unescape(raw_title)
    # 2. Eliminar etiquetas HTML residuales (<i>, <sub>, <sup>, etc.)
    plain = re.sub(r'<[^>]+>', '', unescaped)
    return plain.strip()

def rebuild_abstract_inverted_index(inverted_index):
    """Reconstruye el texto original de un abstract a partir de la estructura invertida de OpenAlex."""
    if not inverted_index:
        return ""
    word_positions = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions[pos] = word
    sorted_words = [word_positions[i] for i in sorted(word_positions.keys())]
    return " ".join(sorted_words)

def get_openalex_paper_data(doi, email, verify_ssl=True):
    """Recupera metadatos detallados de un artículo desde la API de OpenAlex usando su DOI o ID de OpenAlex."""
    clean_doi = doi.replace("https://doi.org/", "").strip()
    if clean_doi.lower().startswith("w") and clean_doi[1:].isdigit():
        url = f"https://api.openalex.org/works/{clean_doi.upper()}"
    else:
        url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
    headers = {}
    if email:
        headers["User-Agent"] = f"mailto:{email}"
    else:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        
    req = urllib.request.Request(url, headers=headers)
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data
    except Exception as e:
        logger.warning(f"[OpenAlex API] Error al recuperar metadatos para DOI {doi}: {e}")
    return None

def get_citing_papers_openalex(doi, email, count=20, verify_ssl=True):
    """Recupera artículos que citan al DOI o ID objetivo en la base de datos de OpenAlex."""
    clean_doi = doi.replace("https://doi.org/", "").strip()
    
    openalex_id = None
    if clean_doi.lower().startswith("w") and clean_doi[1:].isdigit():
        openalex_id = clean_doi.upper()
    else:
        # Resolver DOI -> OpenAlex ID primero para evitar error 400 Bad Request
        paper_data = get_openalex_paper_data(clean_doi, email, verify_ssl=verify_ssl)
        if paper_data:
            full_id = paper_data.get("id", "")
            if full_id:
                openalex_id = full_id.split("/")[-1].upper()
                
    if not openalex_id:
        logger.warning(f"[OpenAlex API] No se pudo resolver el DOI {doi} a un ID de OpenAlex para buscar citantes.")
        return []
        
    url = f"https://api.openalex.org/works?filter=cites:{openalex_id}&per-page={count}"
    headers = {}
    if email:
        headers["User-Agent"] = f"mailto:{email}"
    else:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        
    req = urllib.request.Request(url, headers=headers)
    citing_papers = []
    
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                results = data.get("results", [])
                for work in results:
                    title = _clean_openalex_title(work.get("title", "Sin título"))
                    raw_doi = work.get("doi")
                    if raw_doi:
                        work_doi = raw_doi.replace("https://doi.org/", "").strip()
                    else:
                        # Fallback al ID de OpenAlex (ej: W12345678) si no tiene DOI
                        work_id = work.get("id", "")
                        work_doi = work_id.split("/")[-1] if work_id else ""
                    
                    authorships = work.get("authorships", [])
                    authors_list = [a.get("author", {}).get("display_name", "") for a in authorships]
                    author_name = format_authors_list(authors_list)
                    
                    publication_year = str(work.get("publication_year", "N/A"))
                    try:
                        y = int(publication_year)
                        import datetime
                        if not (1900 <= y <= datetime.datetime.now().year):
                            publication_year = str(get_fallback_year())
                    except (ValueError, TypeError):
                        publication_year = str(get_fallback_year())
                        
                    primary_loc = work.get("primary_location") or {}
                    source = (primary_loc.get("source") or {}) if isinstance(primary_loc, dict) else {}
                    journal = source.get("display_name", "N/A") if isinstance(source, dict) else "N/A"
                    abstract_index = work.get("abstract_inverted_index", {})
                    abstract = rebuild_abstract_inverted_index(abstract_index) if abstract_index else "Abstract no disponible."
                    
                    citing_papers.append({
                        "DOI": work_doi,
                        "Título": title,
                        "Autores": author_name,
                        "Año": publication_year,
                        "Revista": journal,
                        "Abstract": abstract
                    })
    except Exception as e:
        logger.error(f"[OpenAlex API] Error al obtener artículos que citan a {doi}: {e}")
    return citing_papers


def search_openalex_works(query, email, verify_ssl=True, count=30):
    """Busca artículos en OpenAlex que coincidan con la consulta de búsqueda."""
    import urllib.parse
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.openalex.org/works?search={encoded_query}&per-page={count}"
    headers = {"User-Agent": f"mailto:{email}"} if email else {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("results", [])
    except Exception as e:
        logger.warning(f"[OpenAlex API] Error al buscar trabajos para la consulta '{query}': {e}")
    return []
