"""
themes.py — Registro Central de Temas Disciplinarios para bibliometric-analyzer.

Cada tema define columnas de matriz Excel, heurísticas cualitativas,
filtros BFS, y generación de RQs adaptados a la disciplina.
"""

import re
import logging

logger = logging.getLogger("bibliometric_analyzer")

# ─────────────────────────────────────────────────────────
#  Paleta de colores genérica para clusters (8 colores)
# ─────────────────────────────────────────────────────────
CLUSTER_COLORS = [
    "#1B4332",  # Verde bosque
    "#028090",  # Teal
    "#BC6C25",  # Ámbar
    "#A3B18A",  # Salvia
    "#5E548E",  # Púrpura
    "#9B2226",  # Rojo oscuro
    "#0077B6",  # Azul océano
    "#E76F51",  # Coral
]

# ─────────────────────────────────────────────────────────
#  Columnas base (siempre presentes en toda matriz)
# ─────────────────────────────────────────────────────────
BASE_COLUMNS = [
    "#", "ID_OpenAlex", "DOI", "Título", "Autores",
    "Año", "Revista", "Abstract",
    "Descubrimientos Principales", "Aporte al Tema",
]

# ─────────────────────────────────────────────────────────
#  Columnas de calidad (siempre al final de toda matriz)
# ─────────────────────────────────────────────────────────
QUALITY_COLUMNS = [
    "Calidad del Estudio (Alta/Media/Baja)",
    "Riesgo de Sesgo",
    "Nivel de Evidencia",
]

# ─────────────────────────────────────────────────────────
#  Función auxiliar: generar heurísticas genéricas
# ─────────────────────────────────────────────────────────
def _extract_key_terms(title, abstract, n=5):
    """Extrae los n términos más relevantes (no stopwords) del título + abstract."""
    stopwords = {
        "the", "a", "an", "of", "in", "for", "and", "or", "to", "on", "at",
        "by", "with", "from", "is", "are", "was", "were", "this", "that",
        "these", "those", "it", "its", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "will", "would", "could", "should",
        "may", "might", "can", "shall", "not", "no", "nor", "but", "if",
        "than", "then", "so", "as", "such", "both", "each", "all", "any",
        "few", "more", "most", "other", "some", "only", "own", "same",
        "too", "very", "just", "about", "above", "after", "again", "against",
        "between", "into", "through", "during", "before", "under", "over",
        "el", "la", "los", "las", "de", "del", "en", "con", "por", "para",
        "un", "una", "es", "son", "se", "su", "al", "que", "como", "más",
        "pero", "sin", "sobre", "entre", "durante", "desde", "hasta",
        "study", "research", "analysis", "results", "effect", "effects",
        "using", "based", "used", "method", "approach", "paper", "article",
        "however", "also", "well", "two", "three", "new", "different",
        "abstract", "disponible", "nan", "none",
    }
    text = f"{title} {abstract}".lower()
    words = re.findall(r'\b[a-záéíóúñü]{4,}\b', text)
    freq = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    sorted_terms = sorted(freq.items(), key=lambda x: -x[1])
    return [t[0] for t in sorted_terms[:n]]


def _truncate_words(text, max_chars=120):
    """Trunca en límite de palabra, no de carácter. Evita cortes como '...the find.' en vez de '...the findings'."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_space = cut.rfind(' ')
    if last_space > max_chars // 2:
        cut = cut[:last_space]
    return cut.rstrip('.,;')


def _generic_qualitative(title, abstract, discipline_hint=""):
    """Genera descubrimientos y aportes genéricos desde título + abstract."""
    terms = _extract_key_terms(title, abstract)
    terms_str = ", ".join(terms[:3]) if terms else "los temas centrales"
    
    if not abstract or abstract.strip().lower() in ("", "nan", "abstract no disponible.", "n/a"):
        disc = f"Investigación sobre {terms_str} en el contexto de {discipline_hint or 'la disciplina'}."
        aporte = "Contribuye al marco teórico de la investigación con evidencia empírica o teórica."
        return disc, aporte
    
    # Intentar extraer hallazgos del abstract
    abstract_lower = abstract.lower()
    
    # Buscar patrones de resultados — captura hasta fin de oración o 150 chars, luego trunca en palabra
    result_patterns = [
        r'(?:results?\s+(?:show|indicate|demonstrate|reveal|suggest|confirm))\s+([^.]{30,150})',
        r'(?:findings?\s+(?:show|indicate|demonstrate|reveal|suggest))\s+([^.]{30,150})',
        r'(?:we\s+(?:found|observed|demonstrated|showed))\s+([^.]{30,150})',
        r'(?:se\s+(?:encontró|observó|demostró|evidenció))\s+([^.]{30,150})',
        r'(?:los\s+resultados\s+(?:muestran|indican|demuestran|revelan))\s+([^.]{30,150})',
    ]
    
    finding = None
    for pattern in result_patterns:
        match = re.search(pattern, abstract_lower)
        if match:
            # Truncar en límite de palabra, no de carácter
            finding = _truncate_words(match.group(1).strip().rstrip('.'), max_chars=120)
            break
    
    if finding:
        disc = f"Se identificó que {finding}. El estudio aborda {terms_str}."
    else:
        disc = f"Estudio enfocado en {terms_str}. Examina aspectos clave de {discipline_hint or title[:60]}."
    
    aporte = f"Aporta evidencia sobre {terms_str}, fortaleciendo el marco teórico y metodológico de la investigación."
    return disc, aporte


def _phytochemistry_qualitative(title, abstract):
    if not abstract:
        return "Análisis fitoquímico y de inducción de metabolitos secundarios.", "Aporta a la optimización de biosíntesis vegetal."
    
    yield_matches = re.findall(r"(?:\d+(?:\.\d+)?)\s*(?:mg/g|ug/g|g/kg|mg/L|mg\s+g\s*-1)", abstract, re.IGNORECASE)
    hplc_matches = re.findall(r"(?:HPLC|LC-MS|GC-MS|chromatography|cromatografía)", abstract, re.IGNORECASE)
    
    desc_parts = []
    if yield_matches:
        desc_parts.append(f"Reporta rendimientos cuantitativos de metabolitos en rangos de {', '.join(yield_matches[:2])}.")
    if hplc_matches:
        desc_parts.append(f"Valida el perfil fitoquímico mediante técnicas instrumentales: {', '.join(hplc_matches[:2])}.")
    
    if desc_parts:
        discoveries = " ".join(desc_parts)
    else:
        terms = _extract_key_terms(title, abstract)
        terms_str = ", ".join(terms[:3]) if terms else "vicia, faba, dopa"
        discoveries = f"Estudio enfocado en {terms_str}. Examina aspectos clave de la fitoquímica y biotecnología vegetal."
        
    aporte = "Aporta parámetros experimentales y bases de rendimiento para optimizar la elicitación vegetal."
    return discoveries, aporte


# ═══════════════════════════════════════════════════════════
#  REGISTRO DE TEMAS
# ═══════════════════════════════════════════════════════════

THEME_REGISTRY = {

    # ───────────────────────────────────────────────────────
    #  1. GENERAL / MULTIDISCIPLINARIO
    # ───────────────────────────────────────────────────────
    "general": {
        "name": "General / Multidisciplinario",
        "matrix_columns": [
            "Diseño Metodológico",
            "Población / Muestra",
            "Variables Principales",
            "Instrumento / Técnica",
            "Hallazgos Principales",
            "Limitaciones del Estudio",
        ],
        "example_row": {
            "Diseño Metodológico": "Tipo de diseño (ej. Experimental, Descriptivo, Revisión)",
            "Población / Muestra": "Población o muestra estudiada",
            "Variables Principales": "Variables independientes y dependientes",
            "Instrumento / Técnica": "Instrumento o técnica utilizada",
            "Hallazgos Principales": "Resultados clave del estudio",
            "Limitaciones del Estudio": "Limitaciones metodológicas identificadas",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la investigación multidisciplinaria"),
    },

    # ───────────────────────────────────────────────────────
    #  2. FITOQUÍMICA Y BIOTECNOLOGÍA VEGETAL
    # ───────────────────────────────────────────────────────
    "phytochemistry": {
        "name": "Fitoquímica y Biotecnología Vegetal",
        "matrix_columns": [
            "Especie / Variedad Vegetal",
            "Tejido Analizado",
            "Tipo de Elicitor / Precursor",
            "Concentración del Elicitor",
            "Método de Cuantificación / Extracción",
            "Rendimiento del Metabolito Principal (mg/g)",
            "Principal Limitante Fisiológica",
        ],
        "example_row": {
            "Especie / Variedad Vegetal": "Especie (ej. Vicia faba, Mucuna pruriens)",
            "Tejido Analizado": "Tejido (ej. radícula, semilla, brote)",
            "Tipo de Elicitor / Precursor": "Elicitor (ej. L-Tirosina, MeJA, quitosano)",
            "Concentración del Elicitor": "Dosis (ej. 0.2 mM, 100 µM)",
            "Método de Cuantificación / Extracción": "Método (ej. HPLC-UV, LC-MS/MS)",
            "Rendimiento del Metabolito Principal (mg/g)": "Rendimiento (ej. 1.85 mg/g peso seco)",
            "Principal Limitante Fisiológica": "Limitante (ej. degradación por PPO, fitotoxicidad)",
        },
        "qualitative_keywords": {
            "yield": ["mg/g", "ug/g", "g/kg", "mg/l", "mg g-1", "yield", "rendimiento"],
            "analytical": ["hplc", "chromatography", "spectrophotometric", "lc-ms", "quantification"],
            "elicitor": ["elicitor", "elicitation", "tyrosine", "tirosina", "methyl jasmonate",
                         "salicylic acid", "chitosan", "yeast extract", "precursor"],
            "biosynthesis": ["biosynthesis", "pathway", "enzyme", "oxidase", "ppo", "tyrosinase"],
        },
        "bfs_filter_keywords": ["vicia", "faba", "dopa", "tyrosine", "tirosina", "legume", "haba",
                                 "mucuna", "metabolite", "elicit", "phenol"],
        "precursor_keywords": ["tyrosine", "tirosina", "precursor"],
        "generate_qualitative": _phytochemistry_qualitative,
    },

    # ───────────────────────────────────────────────────────
    #  3. INGENIERÍA GENERAL
    # ───────────────────────────────────────────────────────
    "engineering": {
        "name": "Ingeniería y Tecnología",
        "matrix_columns": [
            "Tipo de Sistema / Proceso",
            "Variables de Entrada",
            "Variables de Respuesta",
            "Método de Optimización / Análisis",
            "Resultados Cuantitativos",
            "Limitaciones Técnicas",
        ],
        "example_row": {
            "Tipo de Sistema / Proceso": "Sistema (ej. reactor, circuito, estructura, red)",
            "Variables de Entrada": "Entradas (ej. temperatura, presión, voltaje)",
            "Variables de Respuesta": "Salidas (ej. eficiencia, resistencia, throughput)",
            "Método de Optimización / Análisis": "Método (ej. FEM, DOE, simulación CFD)",
            "Resultados Cuantitativos": "Valores obtenidos con unidades",
            "Limitaciones Técnicas": "Limitaciones del diseño o modelo",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la ingeniería y tecnología"),
    },

    # ───────────────────────────────────────────────────────
    #  4. INGENIERÍA INDUSTRIAL
    # ───────────────────────────────────────────────────────
    "industrial_engineering": {
        "name": "Ingeniería Industrial",
        "matrix_columns": [
            "Proceso / Operación Estudiada",
            "Herramienta / Metodología (Lean/Six Sigma/DOE/TOC)",
            "KPI o Indicador Medido",
            "Mejora Cuantitativa Obtenida",
            "Análisis de Capacidad / Eficiencia",
            "Limitaciones del Estudio",
        ],
        "example_row": {
            "Proceso / Operación Estudiada": "Proceso (ej. línea de ensamblaje, cadena de suministro, almacén)",
            "Herramienta / Metodología (Lean/Six Sigma/DOE/TOC)": "Herramienta (ej. VSM, DMAIC, Taguchi, Kanban, 5S)",
            "KPI o Indicador Medido": "KPI (ej. OEE, lead time, tasa de defectos, Cpk)",
            "Mejora Cuantitativa Obtenida": "Mejora (ej. reducción del 30% en tiempo de ciclo)",
            "Análisis de Capacidad / Eficiencia": "Capacidad (ej. Cp=1.33, eficiencia del 92%)",
            "Limitaciones del Estudio": "Limitaciones (ej. datos de una sola planta, periodo corto)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la ingeniería industrial y optimización de procesos"),
    },

    # ───────────────────────────────────────────────────────
    #  5. CIENCIAS SOCIALES Y EDUCACIÓN
    # ───────────────────────────────────────────────────────
    "social_sciences": {
        "name": "Ciencias Sociales y Educación",
        "matrix_columns": [
            "Población / Contexto Social",
            "Diseño de Investigación",
            "Instrumento de Recolección",
            "Variables / Categorías de Análisis",
            "Hallazgos Principales",
            "Limitaciones Metodológicas",
        ],
        "example_row": {
            "Población / Contexto Social": "Población (ej. estudiantes universitarios, comunidad rural)",
            "Diseño de Investigación": "Diseño (ej. cuasi-experimental, etnográfico, mixto)",
            "Instrumento de Recolección": "Instrumento (ej. encuesta Likert, entrevista semiestructurada)",
            "Variables / Categorías de Análisis": "Variables (ej. motivación, rendimiento académico, percepción)",
            "Hallazgos Principales": "Hallazgos clave del estudio",
            "Limitaciones Metodológicas": "Limitaciones (ej. muestra no probabilística, sesgo de autoselección)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "las ciencias sociales y la educación"),
    },

    # ───────────────────────────────────────────────────────
    #  6. CIENCIAS DE LA SALUD Y MEDICINA
    # ───────────────────────────────────────────────────────
    "health_sciences": {
        "name": "Ciencias de la Salud y Medicina",
        "matrix_columns": [
            "Tipo de Estudio (RCT/Cohorte/Caso-Control/Transversal)",
            "Población / Muestra Clínica",
            "Intervención / Exposición",
            "Desenlace Primario (Outcome)",
            "Resultados Estadísticos (OR/RR/HR/p-value)",
            "Nivel de Evidencia (GRADE)",
            "Limitaciones del Estudio",
        ],
        "example_row": {
            "Tipo de Estudio (RCT/Cohorte/Caso-Control/Transversal)": "Tipo (ej. Ensayo controlado aleatorizado, Cohorte prospectiva)",
            "Población / Muestra Clínica": "Muestra (ej. 150 pacientes con DM2, edad 40-65)",
            "Intervención / Exposición": "Intervención (ej. metformina 500mg vs placebo)",
            "Desenlace Primario (Outcome)": "Outcome (ej. reducción de HbA1c, mortalidad a 5 años)",
            "Resultados Estadísticos (OR/RR/HR/p-value)": "Estadísticos (ej. OR=2.3, IC95%: 1.5-3.6, p<0.001)",
            "Nivel de Evidencia (GRADE)": "GRADE (ej. Alta, Moderada, Baja, Muy Baja)",
            "Limitaciones del Estudio": "Limitaciones (ej. seguimiento corto, pérdida de sujetos)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "las ciencias de la salud y medicina"),
    },

    # ───────────────────────────────────────────────────────
    #  7. CIENCIAS AMBIENTALES Y ECOLOGÍA
    # ───────────────────────────────────────────────────────
    "environmental": {
        "name": "Ciencias Ambientales y Ecología",
        "matrix_columns": [
            "Ecosistema / Área de Estudio",
            "Especies / Variables Ambientales",
            "Método de Muestreo / Análisis",
            "Indicadores Medidos",
            "Resultados Principales",
            "Implicaciones para Conservación",
        ],
        "example_row": {
            "Ecosistema / Área de Estudio": "Ecosistema (ej. bosque tropical, humedal costero, cuenca hídrica)",
            "Especies / Variables Ambientales": "Variables (ej. biodiversidad, pH, DBO, metales pesados)",
            "Método de Muestreo / Análisis": "Método (ej. transectos, GIS, espectroscopía de suelos)",
            "Indicadores Medidos": "Indicadores (ej. índice de Shannon, huella de carbono, ICA)",
            "Resultados Principales": "Resultados clave del estudio",
            "Implicaciones para Conservación": "Implicaciones (ej. corredores ecológicos, restauración)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "las ciencias ambientales y la ecología"),
    },

    # ───────────────────────────────────────────────────────
    #  8. ECONOMÍA Y ADMINISTRACIÓN
    # ───────────────────────────────────────────────────────
    "economics": {
        "name": "Economía y Administración",
        "matrix_columns": [
            "País / Región de Estudio",
            "Periodo de Análisis",
            "Modelo Econométrico / Método",
            "Variables Dependientes e Independientes",
            "Resultados Principales",
            "Implicaciones de Política",
        ],
        "example_row": {
            "País / Región de Estudio": "Región (ej. Perú, LATAM, OCDE, panel de 50 países)",
            "Periodo de Análisis": "Periodo (ej. 2010-2023, datos trimestrales)",
            "Modelo Econométrico / Método": "Modelo (ej. GMM, panel data, VAR, DEA, SEM)",
            "Variables Dependientes e Independientes": "Variables (ej. PIB per cápita ~ inversión + educación)",
            "Resultados Principales": "Coeficientes y significancia estadística",
            "Implicaciones de Política": "Implicaciones (ej. aumento de inversión pública en I+D)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la economía y la administración"),
    },

    # ───────────────────────────────────────────────────────
    #  9. DERECHO Y CIENCIAS JURÍDICAS
    # ───────────────────────────────────────────────────────
    "law": {
        "name": "Derecho y Ciencias Jurídicas",
        "matrix_columns": [
            "Jurisdicción / País",
            "Marco Normativo Analizado",
            "Método Jurídico (Dogmático/Comparado/Empírico)",
            "Tesis / Argumento Central",
            "Hallazgos Principales",
            "Implicaciones Normativas",
        ],
        "example_row": {
            "Jurisdicción / País": "Jurisdicción (ej. Perú, España, Derecho Internacional)",
            "Marco Normativo Analizado": "Norma (ej. Constitución Art. 2, Ley 30364, RGPD)",
            "Método Jurídico (Dogmático/Comparado/Empírico)": "Método (ej. exégesis, hermenéutica, derecho comparado)",
            "Tesis / Argumento Central": "Tesis principal del autor",
            "Hallazgos Principales": "Hallazgos o conclusiones jurídicas",
            "Implicaciones Normativas": "Implicaciones (ej. reforma legislativa, jurisprudencia vinculante)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "el derecho y las ciencias jurídicas"),
    },

    # ───────────────────────────────────────────────────────
    #  10. CIENCIAS DE LA COMPUTACIÓN E IA
    # ───────────────────────────────────────────────────────
    "computer_science": {
        "name": "Ciencias de la Computación e IA",
        "matrix_columns": [
            "Tipo de Modelo / Algoritmo",
            "Dataset / Benchmark Utilizado",
            "Métricas de Evaluación",
            "Resultados Cuantitativos",
            "Comparación con Estado del Arte (SOTA)",
            "Limitaciones Técnicas",
        ],
        "example_row": {
            "Tipo de Modelo / Algoritmo": "Modelo (ej. Transformer, CNN, Random Forest, GAN)",
            "Dataset / Benchmark Utilizado": "Dataset (ej. ImageNet, COCO, GLUE, dataset propio N=10k)",
            "Métricas de Evaluación": "Métricas (ej. Accuracy, F1-score, BLEU, mAP, RMSE)",
            "Resultados Cuantitativos": "Resultados (ej. F1=0.94, Acc=97.2%, latencia 12ms)",
            "Comparación con Estado del Arte (SOTA)": "SOTA (ej. supera baseline en +2.3% F1)",
            "Limitaciones Técnicas": "Limitaciones (ej. requiere GPU A100, no generaliza a otros idiomas)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "las ciencias de la computación e inteligencia artificial"),
    },

    # ───────────────────────────────────────────────────────
    #  11. HOTELERÍA Y TURISMO
    # ───────────────────────────────────────────────────────
    "hospitality": {
        "name": "Hotelería y Turismo",
        "matrix_columns": [
            "Tipo de Establecimiento / Destino",
            "Segmento de Mercado / Perfil del Turista",
            "Metodología (SERVQUAL/HOLSAT/Otro)",
            "Indicadores de Satisfacción / Ocupación",
            "Hallazgos Principales",
            "Implicaciones Gerenciales",
        ],
        "example_row": {
            "Tipo de Establecimiento / Destino": "Establecimiento (ej. hotel 4 estrellas, resort, Airbnb, destino Cusco)",
            "Segmento de Mercado / Perfil del Turista": "Segmento (ej. turismo de aventura, corporativo, millennials)",
            "Metodología (SERVQUAL/HOLSAT/Otro)": "Metodología (ej. SERVQUAL, HOLSAT, NPS, análisis de reviews)",
            "Indicadores de Satisfacción / Ocupación": "Indicadores (ej. RevPAR, tasa de ocupación, NPS=72)",
            "Hallazgos Principales": "Hallazgos clave del estudio",
            "Implicaciones Gerenciales": "Implicaciones (ej. capacitación del personal, pricing dinámico)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la hotelería y el turismo"),
    },

    # ───────────────────────────────────────────────────────
    #  12. GASTRONOMÍA Y RESTAURANTES
    # ───────────────────────────────────────────────────────
    "gastronomy": {
        "name": "Gastronomía y Restaurantes",
        "matrix_columns": [
            "Tipo de Servicio / Concepto Gastronómico",
            "Producto / Insumo Estudiado",
            "Técnica Culinaria / Proceso",
            "Análisis Sensorial / Bromatológico",
            "Indicadores de Calidad / Aceptabilidad",
            "Implicaciones para la Industria",
        ],
        "example_row": {
            "Tipo de Servicio / Concepto Gastronómico": "Concepto (ej. fine dining, comida rápida, cocina fusión, catering)",
            "Producto / Insumo Estudiado": "Producto (ej. quinua, cacao nativo, carnes curadas, fermentados)",
            "Técnica Culinaria / Proceso": "Técnica (ej. sous vide, fermentación, deshidratación, cocción al vacío)",
            "Análisis Sensorial / Bromatológico": "Análisis (ej. panel hedónico 9 puntos, perfil de textura TPA)",
            "Indicadores de Calidad / Aceptabilidad": "Indicadores (ej. aceptabilidad 85%, score sensorial 7.2/9)",
            "Implicaciones para la Industria": "Implicaciones (ej. scalamiento industrial, denominación de origen)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la gastronomía y la industria restaurantera"),
    },

    # ───────────────────────────────────────────────────────
    #  13. CIENCIA Y TECNOLOGÍA DE ALIMENTOS
    # ───────────────────────────────────────────────────────
    "food_science": {
        "name": "Ciencia y Tecnología de Alimentos",
        "matrix_columns": [
            "Matriz Alimentaria",
            "Tratamiento / Proceso Aplicado",
            "Análisis Físico-Químico",
            "Análisis Microbiológico",
            "Vida Útil / Estabilidad",
            "Resultados Principales",
            "Limitaciones del Estudio",
        ],
        "example_row": {
            "Matriz Alimentaria": "Matriz (ej. leche, harina de trigo, jugo de fruta, embutido)",
            "Tratamiento / Proceso Aplicado": "Proceso (ej. pasteurización, liofilización, HPP, encapsulación)",
            "Análisis Físico-Químico": "Análisis (ej. pH, acidez titulable, contenido fenólico, Aw)",
            "Análisis Microbiológico": "Microbiología (ej. recuento aerobio, coliformes, Salmonella ausencia/25g)",
            "Vida Útil / Estabilidad": "Vida útil (ej. 30 días a 4°C, estabilidad acelerada 40°C/75%HR)",
            "Resultados Principales": "Resultados clave del estudio",
            "Limitaciones del Estudio": "Limitaciones (ej. escala laboratorio, una sola matriz)",
        },
        "qualitative_keywords": {},
        "bfs_filter_keywords": [],
        "precursor_keywords": [],
        "generate_qualitative": lambda t, a: _generic_qualitative(t, a, "la ciencia y tecnología de alimentos"),
    },
}


def get_theme(theme_name):
    """Obtiene un tema del registro. Retorna 'general' si no existe."""
    if theme_name not in THEME_REGISTRY:
        logger.warning(f"Tema '{theme_name}' no encontrado. Usando 'general'.")
        return THEME_REGISTRY["general"]
    return THEME_REGISTRY[theme_name]


def get_all_theme_names():
    """Retorna lista de todos los nombres de temas disponibles."""
    return list(THEME_REGISTRY.keys())


def get_theme_columns(theme_name):
    """Retorna BASE_COLUMNS + columnas del tema + QUALITY_COLUMNS."""
    theme = get_theme(theme_name)
    return BASE_COLUMNS + theme["matrix_columns"] + QUALITY_COLUMNS


def generate_qualitative_for_theme(theme_name, title, abstract):
    """Genera descubrimientos y aportes usando la función del tema."""
    theme = get_theme(theme_name)
    gen_fn = theme.get("generate_qualitative")
    if gen_fn:
        return gen_fn(title, abstract)
    return _generic_qualitative(title, abstract)
