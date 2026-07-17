import urllib.request
import urllib.parse
import json
import logging
import re
import xml.etree.ElementTree as ET
from .utils import parse_author_name, format_authors_list, get_fallback_year, get_ssl_context

logger = logging.getLogger("bibliometric_analyzer")

def _make_entrez_request(endpoint, params, api_key=None, verify_ssl=True):
    """Realiza una petición HTTP helper a las APIs de NCBI Entrez."""
    base_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/{endpoint}"
    
    # Agregar la clave de API si está configurada
    if api_key:
        params["api_key"] = api_key
        
    req_url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(req_url, headers={"User-Agent": "Mozilla/5.0"})
    
    ctx = get_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                return response.read()
    except Exception as e:
        logger.error(f"[PubMed API] Fallo al consultar {endpoint}: {e}")
    return None

def get_pmid_by_doi(doi, api_key=None, verify_ssl=True):
    """Busca el PMID (PubMed ID) correspondiente a un DOI."""
    clean_doi = doi.replace("https://doi.org/", "").strip()
    params = {
        "db": "pubmed",
        "term": f'"{clean_doi}"[Location ID]',
        "retmode": "json"
    }
    response = _make_entrez_request("esearch.fcgi", params, api_key, verify_ssl=verify_ssl)
    if response:
        try:
            data = json.loads(response.decode("utf-8"))
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if id_list:
                return id_list[0]
        except Exception as e:
            logger.debug(f"[PubMed API] Error al deserializar esearch para DOI {doi}: {e}")
    return None

def get_pubmed_abstract(pmid, api_key=None, verify_ssl=True):
    """Obtiene el abstract de PubMed usando efetch (formato XML)."""
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "rettype": "abstract"
    }
    response = _make_entrez_request("efetch.fcgi", params, api_key, verify_ssl=verify_ssl)
    if response:
        try:
            # Parsear XML con expresión regular ligera para evitar fallos de parseo strict de XML
            xml_str = response.decode("utf-8", errors="replace")
            # Buscar todas las etiquetas AbstractText
            abstract_parts = re.findall(r'<AbstractText[^>]*>(.*?)</AbstractText>', xml_str, re.DOTALL)
            if abstract_parts:
                # Quitar etiquetas internas (como <b>, <i>, etc.)
                clean_parts = [re.sub(r'<[^>]+>', '', part).strip() for part in abstract_parts]
                return " ".join(clean_parts)
        except Exception as e:
            logger.debug(f"[PubMed API] Error al extraer abstract de XML para PMID {pmid}: {e}")
    return "Abstract no disponible (PubMed)."

def get_pubmed_paper_data(pmid_or_doi, api_key=None, verify_ssl=True):
    """
    Obtiene los metadatos de un artículo en PubMed.
    Si se provee un DOI, primero busca su PMID.
    """
    pmid = pmid_or_doi
    # Si parece un DOI, buscar el PMID primero
    if "/" in pmid_or_doi or pmid_or_doi.startswith("10."):
        pmid = get_pmid_by_doi(pmid_or_doi, api_key, verify_ssl=verify_ssl)
        if not pmid:
            logger.debug(f"[PubMed API] No se encontró PMID para DOI {pmid_or_doi}")
            return None

    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "json"
    }
    response = _make_entrez_request("esummary.fcgi", params, api_key, verify_ssl=verify_ssl)
    if not response:
        return None
        
    try:
        data = json.loads(response.decode("utf-8"))
        result = data.get("result", {})
        uid = result.get("uids", [None])[0]
        if not uid:
            return None
            
        summary = result.get(uid, {})
        title = summary.get("title", "Sin título")
        
        # Parsear autores
        authors = summary.get("authors", [])
        authors_list = [a.get("name", "") for a in authors]
        author_name = format_authors_list(authors_list)
        
        # Año
        pub_date = summary.get("pubdate", "")
        year_match = re.search(r'\b(19|20)\d{2}\b', pub_date)
        year = year_match.group(0) if year_match else str(get_fallback_year())
        
        journal = summary.get("source", "N/A")
        
        # Recuperar DOI de los articleids
        doi = ""
        for aid in summary.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
                break
        if not doi:
            doi = pmid_or_doi if "/" in pmid_or_doi else f"PubMed_PMID_{pmid}"
            
        # El abstract no viene en esummary, hay que pedirlo a efetch
        abstract = get_pubmed_abstract(pmid, api_key, verify_ssl=verify_ssl)
        
        return {
            "PMID": pmid,
            "DOI": doi,
            "Título": title,
            "Autores": author_name,
            "Año": year,
            "Revista": journal,
            "Abstract": abstract
        }
    except Exception as e:
        logger.error(f"[PubMed API] Error al parsear esummary para {pmid_or_doi}: {e}")
    return None

def get_citing_papers_pubmed(doi_or_pmid, api_key=None, count=20, verify_ssl=True):
    """
    Busca artículos que citan al artículo objetivo en PubMed LinkOut / Entrez Links.
    """
    pmid = doi_or_pmid
    if "/" in doi_or_pmid or doi_or_pmid.startswith("10."):
        pmid = get_pmid_by_doi(doi_or_pmid, api_key, verify_ssl=verify_ssl)
        if not pmid:
            return []

    params = {
        "dbfrom": "pubmed",
        "db": "pubmed",
        "linkname": "pubmed_pubmed_citedin",
        "id": pmid,
        "retmode": "json"
    }
    response = _make_entrez_request("elink.fcgi", params, api_key, verify_ssl=verify_ssl)
    citing_papers = []
    
    if not response:
        return []
        
    try:
        data = json.loads(response.decode("utf-8"))
        linksets = data.get("linksets", [])
        if not linksets:
            return []
            
        linksetdbs = linksets[0].get("linksetdbs", [])
        if not linksetdbs:
            return []
            
        # Extraer PMIDs citantes
        citing_ids = linksetdbs[0].get("links", [])
        if not citing_ids:
            return []
            
        # Limitar número de citantes
        target_ids = citing_ids[:count]
        
        # Consultar la información en batch para no quemar la API
        params_summary = {
            "db": "pubmed",
            "id": ",".join(target_ids),
            "retmode": "json"
        }
        summary_resp = _make_entrez_request("esummary.fcgi", params_summary, api_key, verify_ssl=verify_ssl)
        if summary_resp:
            summary_data = json.loads(summary_resp.decode("utf-8"))
            result = summary_data.get("result", {})
            uids = result.get("uids", [])
            for uid in uids:
                summary = result.get(uid, {})
                title = summary.get("title", "Sin título")
                
                # Autores
                authors = summary.get("authors", [])
                authors_list = [a.get("name", "") for a in authors]
                author_name = format_authors_list(authors_list)
                
                # Año
                pub_date = summary.get("pubdate", "")
                year_match = re.search(r'\b(19|20)\d{2}\b', pub_date)
                year = year_match.group(0) if year_match else str(get_fallback_year())
                
                journal = summary.get("source", "N/A")
                
                # DOI
                work_doi = ""
                for aid in summary.get("articleids", []):
                    if aid.get("idtype") == "doi":
                        work_doi = aid.get("value", "")
                        break
                if not work_doi:
                    work_doi = f"pmid:{uid}"
                    
                abstract = get_pubmed_abstract(uid, api_key, verify_ssl=verify_ssl)
                
                citing_papers.append({
                    "DOI": work_doi,
                    "Título": title,
                    "Autores": author_name,
                    "Año": year,
                    "Revista": journal,
                    "Abstract": abstract
                })
    except Exception as e:
        logger.error(f"[PubMed API] Error al obtener citantes en PubMed para {doi_or_pmid}: {e}")
        
    return citing_papers

def search_pubmed_works(query, api_key=None, count=5, verify_ssl=True):
    """Busca artículos en PubMed para una consulta de texto libre y retorna una lista de metadatos básicos."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": count,
        "retmode": "json"
    }
    response = _make_entrez_request("esearch.fcgi", params, api_key, verify_ssl=verify_ssl)
    results = []
    if response:
        try:
            data = json.loads(response.decode("utf-8"))
            id_list = data.get("esearchresult", {}).get("idlist", [])
            for pmid in id_list:
                paper = get_pubmed_paper_data(pmid, api_key, verify_ssl=verify_ssl)
                if paper:
                    results.append({
                        "doi": paper.get("DOI", ""),
                        "title": paper.get("Título", "Sin título"),
                        "authors": paper.get("Autores", "Desconocido"),
                        "year": paper.get("Año", "N/A"),
                        "journal": paper.get("Revista", "N/A"),
                        "abstract": paper.get("Abstract", ""),
                        "pmid": pmid
                    })
        except Exception as e:
            logger.error(f"[PubMed API] Error en búsqueda general para '{query}': {e}")
    return results
