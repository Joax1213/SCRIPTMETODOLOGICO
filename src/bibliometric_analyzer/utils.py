import re
import json
import ssl
import logging
import datetime
from pathlib import Path

# Configuración del logger global del paquete
logger = logging.getLogger("bibliometric_analyzer")

def setup_logging(verbose=False):
    """Configura el logging para la CLI."""
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Evitar duplicar handlers
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

def get_fallback_year():
    """Retorna el año actual dinámicamente como valor por defecto."""
    return datetime.date.today().year

SURNAME_PARTICLES = {"de", "del", "da", "das", "dos", "du", "von", "van", "der", "di", "la", "le"}

def parse_author_name(creator):
    """
    Normaliza y formatea un nombre de autor en formato 'Apellido, I.' (iniciales).
    Soporta apellidos simples y compuestos con partículas (de, da, dos, von, etc.).
    """
    if not creator or str(creator).strip() == "" or str(creator).strip().lower() in ("desconocido", "nan", "none"):
        return "Desconocido"
    
    creator = str(creator).strip()
    
    # Si ya contiene comas (formato típico 'Apellido, Nombre')
    if "," in creator:
        parts = creator.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip()
        
        # Extraer primera inicial válida ignorando partículas si estuvieran en el primer nombre
        first_tokens = [t for t in first.split() if t.lower() not in SURNAME_PARTICLES]
        first_init = f"{first_tokens[0][0].upper()}." if (first_tokens and first_tokens[0]) else (f"{first[0].upper()}." if first else "")
        return f"{last}, {first_init}"
    
    # Formato simple sin comas (p.ej., 'Carlos dos Santos', 'Gabriel Garcia Marquez', 'Etemadi F.')
    parts = creator.split()
    if len(parts) == 0:
        return "Desconocido"
    elif len(parts) == 1:
        return parts[0]
    else:
        # Heurística para iniciales al final sin coma (ej. 'Etemadi F.', 'Etemadi F.J.', 'Etemadi FJ')
        last_token = parts[-1]
        last_token_clean = last_token.replace(".", "")
        if last_token_clean.isupper() and len(last_token_clean) <= 3:
            surname = " ".join(parts[:-1])
            formatted_initials = "".join([f"{char}." for char in last_token_clean])
            return f"{surname}, {formatted_initials}"
            
        # Detectar partículas al final que forman parte del apellido (ej: ["Carlos", "dos", "Santos"])
        surname_tokens = [parts[-1]]
        idx = len(parts) - 2
        while idx > 0 and parts[idx].lower() in SURNAME_PARTICLES:
            surname_tokens.insert(0, parts[idx])
            idx -= 1
            
        last_name = " ".join(surname_tokens)
        first_names = parts[:idx + 1]
        
        initials_list = []
        for n in first_names:
            if n.lower() not in SURNAME_PARTICLES and len(n) > 0:
                clean_n = n.replace(".", "")
                if clean_n:
                    initials_list.append(f"{clean_n[0].upper()}.")
                    
        initials = "".join(initials_list)
        if not initials and first_names:
            initials = f"{first_names[0][0].upper()}."
            
        return f"{last_name}, {initials}"

def format_authors_list(authors_list, max_authors=5):
    """
    Toma una lista de nombres de autores y los une en formato corto
    preservando la co-autoría.
    """
    if not authors_list:
        return "Desconocido"
    
    parsed = [parse_author_name(a) for a in authors_list if a]
    parsed = [p for p in parsed if p != "Desconocido"]
    
    if not parsed:
        return "Desconocido"
    
    if len(parsed) <= max_authors:
        return ", ".join(parsed)
    else:
        return ", ".join(parsed[:max_authors]) + " et al."


def get_short_author(authors_str):
    """
    Retorna el apellido del primer autor. Si hay más de un autor,
    agrega 'et al.'. Evita 'et al.' para autores únicos (L-9).
    """
    if not authors_str or authors_str == "Desconocido":
        return "Desconocido"
        
    if "et al." in authors_str:
        clean = authors_str.split("et al.")[0].strip()
        parts = [p.strip() for p in clean.split(",") if p.strip()]
        if parts:
            first_author = parts[0]
            # Si tiene coma interna en el nombre del primer autor, ej "Joaquín, J."
            if " " in first_author:
                first_author = first_author.split()[0]
            return f"{first_author} et al."
        return "Desconocido"
        
    parts = [p.strip() for p in authors_str.split(",") if p.strip()]
    
    # Reagrupar autores
    authors = []
    i = 0
    while i < len(parts):
        if i > 0 and (len(parts[i]) <= 3 and parts[i].endswith(".")):
            authors[-1] = f"{authors[-1]}, {parts[i]}"
        else:
            authors.append(parts[i])
        i += 1
        
    if not authors:
        return "Desconocido"
        
    first_author = authors[0].split(",")[0].strip()
    # Si tiene espacios, tomamos solo el apellido (primer token)
    if " " in first_author:
        first_author = first_author.split()[0]
        
    if len(authors) == 1:
        return first_author
    else:
        return f"{first_author} et al."


class JSONCache:
    """Clase para administrar la caché local de respuestas de APIs."""
    def __init__(self, cache_dir=None):
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Por defecto guardamos la caché en el home del usuario ~/.bibliometric_cache/
            self.cache_dir = Path.home() / ".bibliometric_cache"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directorio de caché configurado en: {self.cache_dir}")

    def _sanitize_filename(self, key):
        """Sanitiza una clave (como un DOI o EID) para que sea un nombre de archivo válido."""
        # Reemplaza caracteres no permitidos
        sanitized = re.sub(r'[^a-zA-Z0-9_\-.]', '_', key)
        return sanitized + ".json"

    def get(self, api_name, key):
        """Recupera un elemento de la caché si existe y no ha expirado."""
        if not key:
            return None
        
        file_path = self.cache_dir / api_name / self._sanitize_filename(key)
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # Comprobar expiración (ej. 7 días)
                cached_time = data.get("_cached_at")
                if cached_time:
                    cached_dt = datetime.datetime.fromisoformat(cached_time)
                    age = datetime.datetime.now() - cached_dt
                    if age.days < 7: # Caché válida por 7 días
                        logger.debug(f"[Caché] Hit para {api_name} - {key}")
                        return data.get("payload")
                    else:
                        logger.debug(f"[Caché] Expired para {api_name} - {key}")
            except Exception as e:
                logger.warning(f"Error al leer caché para {key}: {e}")
        return None

    def set(self, api_name, key, payload):
        """Guarda un elemento en la caché."""
        if not key or payload is None:
            return
            
        api_dir = self.cache_dir / api_name
        api_dir.mkdir(exist_ok=True)
        
        file_path = api_dir / self._sanitize_filename(key)
        data = {
            "_cached_at": datetime.datetime.now().isoformat(),
            "payload": payload
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[Caché] Guardado para {api_name} - {key}")
        except Exception as e:
            logger.warning(f"Error al escribir caché para {key}: {e}")

    def clear(self):
        """Limpia todo el directorio de caché."""
        try:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Caché limpiada con éxito.")
        except Exception as e:
            logger.error(f"Error al limpiar la caché: {e}")

def get_ssl_context(verify=True):
    """Retorna un contexto SSL con verificación activa o desactivada según el parámetro."""
    if verify:
        return ssl.create_default_context()
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
