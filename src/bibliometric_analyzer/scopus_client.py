import urllib.request
import urllib.parse
import json
import logging
import ssl
from .utils import parse_author_name, get_fallback_year, get_ssl_context

logger = logging.getLogger("bibliometric_analyzer")

def get_scopus_paper_data(doi, api_key, verify_ssl=True):
    """Recupera metadatos básicos de un artículo en Scopus usando su DOI."""
    if not api_key:
        logger.debug("[Scopus API] No se puede buscar: Falta SCOPUS_API_KEY")
        return None
        
    clean_doi = doi.replace("https://doi.org/", "").strip()
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json"
    }
    params = {
        "query": f'DOI("{clean_doi}")',
        "count": 1
    }
    req_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(req_url, headers=headers)
    
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                entries = data.get("search-results", {}).get("entry", [])
                if entries and "error" not in entries[0]:
                    return entries[0]
    except Exception as e:
        logger.warning(f"[Scopus API] Error al recuperar metadatos para DOI {doi}: {e}")
    return None

def get_scopus_abstract(eid, api_key, verify_ssl=True):
    """Recupera el abstract de un artículo usando su EID (Elsevier ID)."""
    if not eid or not api_key:
        return None
        
    url = f"https://api.elsevier.com/content/abstract/eid/{eid}"
    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json"
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                coredata = data.get("abstracts-retrieval-response", {}).get("coredata", {})
                description = coredata.get("dc:description", "")
                if description:
                    return description
    except Exception as e:
        logger.debug(f"[Scopus API] No se pudo recuperar abstract para EID {eid}: {e}")
    return None

def get_citing_papers_scopus(doi, title, api_key, verbose=False, verify_ssl=True):
    """
    Busca artículos que citan a la semilla en Scopus.
    Prioriza buscar por DOI mediante REFDOI para máxima precisión, 
    y hace fallback a REFTITLE si es necesario.
    """
    if not api_key:
        logger.debug("[Scopus API] Búsqueda de citantes inactiva (Falta API Key)")
        return []

    url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json"
    }

    # Determinación de query precisa (REFTITLE es el operador soportado por Scopus Search API para citantes)
    if title and title != "Sin título":
        # Truncar a las primeras 8 palabras para evitar conflictos con caracteres
        # especiales de la Scopus Query Language (paréntesis, asteriscos, dos puntos, etc.)
        title_words = title.split()[:8]
        short_title = " ".join(title_words)
        escaped_title = short_title.replace('"', '\\"')
        query = f'REFTITLE("{escaped_title}")'
    elif doi:
        clean_doi = doi.replace("https://doi.org/", "").strip()
        query = f'REF("{clean_doi}")'
    else:
        return []

    params = {
        "query": query,
        "count": 20
    }
    req_url = f"{url}?{urllib.parse.urlencode(params)}"
    if verbose:
        logger.info(f"[Scopus API] Buscando citantes con query: {query}")
        
    req = urllib.request.Request(req_url, headers=headers)
    citing_papers = []
    
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                results = data.get("search-results", {})
                entries = results.get("entry", [])
                
                if entries and entries[0].get("error") == "Result set was empty":
                    logger.debug("[Scopus API] No se encontraron citas para esta consulta en Scopus.")
                    return []
                
                for entry in entries:
                    if not entry or "error" in entry:
                        continue
                    work_doi = entry.get("prism:doi", "")
                    work_id = work_doi if work_doi else entry.get("eid", "")
                    if not work_id:
                        continue
                    
                    work_title = entry.get("dc:title", "Sin título")
                    creator = entry.get("dc:creator", "Desconocido")
                    author_name = parse_author_name(creator)
                    
                    cover_date = entry.get("prism:coverDate", "")
                    publication_year = cover_date.split("-")[0] if "-" in cover_date else str(get_fallback_year())
                    journal = entry.get("prism:publicationName", "N/A")
                    
                    eid = entry.get("eid")
                    abstract = "Abstract no disponible."
                    if eid:
                        abstract = get_scopus_abstract(eid, api_key, verify_ssl=verify_ssl) or "Abstract no disponible (Scopus)."
                        
                    citing_papers.append({
                        "DOI": work_id,
                        "Título": work_title,
                        "Autores": author_name,
                        "Año": publication_year,
                        "Revista": journal,
                        "Abstract": abstract
                    })
    except Exception as e:
        logger.error(f"[Scopus API] Error al obtener citantes para '{title or doi}': {e}")
    return citing_papers
