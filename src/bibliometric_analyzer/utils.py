import os
import re
import json
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

def parse_author_name(creator):
    """
    Normaliza y formatea un nombre de autor en formato 'Apellido, I.' (iniciales).
    Soporta apellidos simples y compuestos.
    """
    if not creator or creator == "Desconocido":
        return "Desconocido"
    
    creator = creator.strip()
    
    # Si ya contiene comas (formato típico 'Apellido, Nombre')
    if "," in creator:
        parts = creator.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip()
        first_init = f"{first[0]}." if first else ""
        return f"{last}, {first_init}"
    
    # Formato simple sin comas (p.ej., 'Gabriel Garcia Marquez', 'John Doe' o 'Etemadi F.')
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
            
        # Fallback occidental estándar: asumimos el último token como apellido y el resto nombres
        first_names = parts[:-1]
        last_name = parts[-1]
        initials = "".join([f"{n[0]}." for n in first_names])
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
    import ssl
    if verify:
        return ssl.create_default_context()
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
