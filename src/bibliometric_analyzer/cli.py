import os
import sys
import argparse
import logging
import shutil

from dotenv import load_dotenv

from .utils import setup_logging, JSONCache
from .lineage_engine import execute_live_lineage, validate_paper_criteria
from .r_bridge import find_rscript_path, ensure_r_packages, run_biblioshiny, run_r_report, run_r_native_analysis
from .matrix_generator import generate_audit_matrix_template, run_interactive_prisma_flow, generate_populated_matrix
from .scopus_client import get_scopus_paper_data, get_scopus_abstract
from .openalex_client import get_openalex_paper_data, rebuild_abstract_inverted_index, search_openalex_works
from .pubmed_client import get_pubmed_paper_data, search_pubmed_works
from .themes import get_all_theme_names

logger = logging.getLogger("bibliometric_analyzer")

def verify_metadata_flow(doi, scopus_key, pubmed_key, contact_email, verbose=False, verify_ssl=True):
    print("=" * 60)
    print(f"AUDITORÍA DE METADATOS PARA DOI: {doi}")
    print("=" * 60)
    
    print("\n1. CONSULTANDO SCOPUS SEARCH API...")
    if scopus_key:
        scopus_entry = get_scopus_paper_data(doi, scopus_key, verify_ssl=verify_ssl)
        if scopus_entry:
            print("   [+] Éxito: Artículo encontrado en Scopus.")
            print(f"       Título: {scopus_entry.get('dc:title', 'N/A')}")
            print(f"       Autores: {scopus_entry.get('dc:creator', 'N/A')}")
            print(f"       Fecha: {scopus_entry.get('prism:coverDate', 'N/A')}")
            print(f"       Revista: {scopus_entry.get('prism:publicationName', 'N/A')}")
            print(f"       EID: {scopus_entry.get('eid', 'N/A')}")
            eid = scopus_entry.get("eid")
            if eid:
                abstract = get_scopus_abstract(eid, scopus_key, verify_ssl=verify_ssl)
                print(f"       Abstract disponible: {'Sí (' + str(len(abstract)) + ' chars)' if abstract else 'No'}")
        else:
            print("   [-] Artículo no encontrado en Scopus o error de conexión.")
    else:
        print("   [!] Scopus deshabilitado (Falta SCOPUS_API_KEY).")

    print("\n2. CONSULTANDO OPENALEX API...")
    alex_data = get_openalex_paper_data(doi, contact_email, verify_ssl=verify_ssl)
    if alex_data:
        print("   [+] Éxito: Artículo encontrado en OpenAlex.")
        print(f"       Título: {alex_data.get('title', 'N/A')}")
        authorships = alex_data.get("authorships", [])
        print(f"       Co-autores: {len(authorships)} registrados")
        print(f"       Año: {alex_data.get('publication_year', 'N/A')}")
        print(f"       Fuente: {alex_data.get('primary_location', {}).get('source', {}).get('display_name', 'N/A')}")
        print(f"       Referencias: {len(alex_data.get('referenced_works', []))} obras referenciadas")
        print(f"       Citaciones registradas: {alex_data.get('cited_by_count', 'N/A')}")
        abs_data = rebuild_abstract_inverted_index(alex_data.get("abstract_inverted_index")) if "abstract_inverted_index" in alex_data else None
        print(f"       Abstract disponible: {'Sí (' + str(len(abs_data)) + ' chars)' if abs_data else 'No'}")
    else:
        print("   [-] Artículo no encontrado en OpenAlex o error de conexión.")

    print("\n3. CONSULTANDO PUBMED API...")
    if pubmed_key:
        print("   [*] Usando NCBI API Key configurada.")
    pubmed_data = get_pubmed_paper_data(doi, pubmed_key, verify_ssl=verify_ssl)
    if pubmed_data:
        print("   [+] Éxito: Artículo encontrado en PubMed.")
        print(f"       PMID: {pubmed_data.get('PMID', 'N/A')}")
        print(f"       Título: {pubmed_data.get('Título', 'N/A')}")
        print(f"       Autores: {pubmed_data.get('Autores', 'N/A')}")
        print(f"       Año: {pubmed_data.get('Año', 'N/A')}")
        print(f"       Revista: {pubmed_data.get('Revista', 'N/A')}")
        abstract = pubmed_data.get("Abstract", "")
        print(f"       Abstract disponible: {'Sí (' + str(len(abstract)) + ' chars)' if abstract and 'no disponible' not in abstract.lower() else 'No'}")
    else:
        print("   [-] Artículo no encontrado en PubMed o error de conexión.")
    print("\n" + "=" * 60)


def install_dependencies():
    import subprocess
    logger.info("Instalando dependencias requeridas...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "pandas", "openpyxl", "networkx", "pypdf", "python-dotenv", "requests"])
        logger.info("¡Dependencias instaladas con éxito!")
    except Exception as e:
        logger.error(f"Error al instalar dependencias: {e}")
        sys.exit(1)

def check_dependencies():
    # Mapa: nombre_display -> nombre_de_import (resuelve ambigüedades como python-dotenv -> dotenv)
    dep_import_map = {
        "pandas": "pandas",
        "openpyxl": "openpyxl",
        "networkx": "networkx",
        "pypdf": "pypdf",
        "python-dotenv": "dotenv",
        "requests": "requests",
    }
    missing = []
    for display_name, import_name in dep_import_map.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(display_name)
    if missing:
        logger.warning(f"Faltan dependencias: {', '.join(missing)}")
        logger.info("Ejecuta `--install-deps` para instalarlas automáticamente.")
        return False
    else:
        logger.info("Todas las dependencias están instaladas correctamente.")
        return True


def _find_pandoc():
    pandoc = shutil.which("pandoc")
    if pandoc:
        return pandoc
    
    import glob
    winget_pattern = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages", "JohnMacFarlane.Pandoc*", "pandoc-*"
    )
    matches = glob.glob(winget_pattern)
    if matches:
        return matches[-1]
    return None


def load_environment_variables():
    load_dotenv()
    if not os.environ.get("SCOPUS_API_KEY") or not os.environ.get("CONTACT_EMAIL"):
        _env_fallback = os.path.join(os.path.expanduser("~"), ".bibliometric_analyzer", ".env")
        if os.path.exists(_env_fallback):
            load_dotenv(dotenv_path=_env_fallback, override=False)

def main():
    load_environment_variables()
    pandoc_dir = _find_pandoc()
    if pandoc_dir:
        parent_dir = os.path.dirname(pandoc_dir) if not os.path.isdir(pandoc_dir) else pandoc_dir
        if parent_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + parent_dir

    parser = argparse.ArgumentParser(
        description="Bibliometric Analyzer — Science Lineage & Bibliometrics CLI"
    )

    # General
    parser.add_argument("--install-deps", action="store_true",
                        help="Instala las dependencias requeridas (pandas, networkx, etc.)")
    parser.add_argument("--check-dependencies", action="store_true",
                        help="Valida la instalación de dependencias")
    parser.add_argument("--verbose", action="store_true",
                        help="Activa el modo verbose con logs detallados")
    parser.add_argument("--max-total-nodes", type=int, default=150,
                        help="Límite máximo de nodos a procesar en total (por defecto: 150)")
    parser.add_argument("--verify-ssl", action="store_true", default=True,
                        help="Habilita la verificación SSL (por defecto: True)")
    parser.add_argument("--no-verify-ssl", action="store_false", dest="verify_ssl",
                        help="Deshabilita la verificación SSL")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Limpia la caché local de consultas de API")
    parser.add_argument("--pipeline", action="store_true",
                        help="Ejecuta la secuencia completa de investigación automatizada")
    parser.add_argument("--search-query", type=str, default=None,
                        help="Consulta de búsqueda para encontrar el paper semilla")
    parser.add_argument("--cache-dir", type=str, default=None,
                        help="Directorio de caché personalizado")

    # API Source
    parser.add_argument("--api-source", type=str, default="all",
                        choices=["openalex", "scopus", "pubmed", "all"],
                        help="Fuente(s) de API a utilizar (por defecto: all)")

    # Linaje
    parser.add_argument("--linaje", action="store_true",
                        help="Ejecuta rastreo de linaje científico por DOI")
    parser.add_argument("--doi", type=str,
                        help="DOI semilla para el linaje o para la etapa 1 del pipeline")
    parser.add_argument("--seed-mode", type=str, default="search",
                        choices=["search", "doi"],
                        help="Modo de entrada de semilla: 'search' (búsqueda automática), 'doi' (DOI aportado por el usuario)")
    parser.add_argument("--max-refs", type=int, default=12,
                        help="Número máximo de referencias ancestro (por defecto: 12)")
    parser.add_argument("--depth", type=int, default=1,
                        help="Profundidad recursiva del linaje (por defecto: 1)")
    parser.add_argument("--full-text", action="store_true",
                        help="Descarga y lee texto completo de PDFs en Open Access")
    parser.add_argument("--pdf-dir", type=str,
                        help="Carpeta local con PDFs offline")
    parser.add_argument("--theme", type=str, default="general",
                        choices=get_all_theme_names(),
                        help=f"Tema de análisis disciplinario (opciones: {', '.join(get_all_theme_names())})")
    parser.add_argument("--start-year", type=int, default=None,
                        help="Año de inicio para filtrar (opcional)")
    parser.add_argument("--end-year", type=int, default=None,
                        help="Año de fin para filtrar (opcional)")
    parser.add_argument("--precursor-filter", action="store_true",
                        help="Activa el filtrado de precursores y sus concentraciones")

    # Salidas
    parser.add_argument("--output-html", type=str,
                        help="Ruta del visor HTML interactivo de salida")
    parser.add_argument("--output-md", type=str,
                        help="Ruta de la base de conocimiento Markdown de salida")
    parser.add_argument("--output", type=str,
                        help="Ruta de archivo de salida general (Excel)")
    parser.add_argument("--output-dir", type=str,
                        help="Carpeta de salida para todos los archivos generados")

    # Motores batch
    parser.add_argument("--input", type=str,
                        help="Ruta de archivo de entrada para motores batch")

    # Revisión Sistemática
    parser.add_argument("--generate-matrix", action="store_true",
                        help="Genera plantilla Excel de auditoría estructurada")
    parser.add_argument("--prisma-flow", action="store_true",
                        help="Asistente interactivo de flujo PRISMA")
    parser.add_argument("--verify-metadata", action="store_true",
                        help="Audita metadatos por API")

    # R Integration
    parser.add_argument("--check-r", action="store_true",
                        help="Verifica e instala dependencias nativas de R")
    parser.add_argument("--biblioshiny", action="store_true",
                        help="Lanza Biblioshiny en R")
    parser.add_argument("--r-native", action="store_true",
                        help="Ejecuta el análisis cienciométrico nativo de R")
    parser.add_argument("--r-report", action="store_true",
                        help="Genera reporte formal R Markdown")

    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    scopus_key = os.environ.get("SCOPUS_API_KEY", "")
    pubmed_key = os.environ.get("NCBI_API_KEY") or os.environ.get("PUBMED_API_KEY") or ""
    contact_email = os.environ.get("CONTACT_EMAIL", "")

    if not scopus_key:
        logger.info("[Config] SCOPUS_API_KEY no configurada. Scopus deshabilitado.")
    if not pubmed_key:
        logger.info("[Config] NCBI_API_KEY/PUBMED_API_KEY no configuradas. PubMed usará velocidad reducida.")
    if not contact_email:
        logger.info("[Config] CONTACT_EMAIL no configurado. OpenAlex usará User-Agent genérico.")

    cache = JSONCache(cache_dir=args.cache_dir)
    if args.clear_cache:
        cache.clear()
        logger.info("Caché eliminada exitosamente.")
        sys.exit(0)

    if args.install_deps:
        install_dependencies()
        sys.exit(0)

    if args.check_dependencies:
        check_dependencies()
        sys.exit(0)

    if args.generate_matrix:
        generate_audit_matrix_template(args.output, args.theme)
        sys.exit(0)

    if args.prisma_flow:
        run_interactive_prisma_flow(args.output)
        sys.exit(0)

    if args.verify_metadata:
        if not args.doi:
            logger.error("Error: Se requiere `--doi` para verificar metadatos.")
            sys.exit(1)
        verify_metadata_flow(args.doi, scopus_key, pubmed_key, contact_email, verbose=args.verbose, verify_ssl=args.verify_ssl)
        sys.exit(0)

    rscript_path = find_rscript_path()

    if args.check_r:
        ensure_r_packages(rscript_path)
        sys.exit(0)

    if args.biblioshiny:
        ensure_r_packages(rscript_path)
        run_biblioshiny(rscript_path)
        sys.exit(0)

    if args.r_report:
        ensure_r_packages(rscript_path)
        run_r_report(rscript_path, args.input, args.output_html)
        sys.exit(0)

    if args.r_native:
        ensure_r_packages(rscript_path)
        run_r_native_analysis(rscript_path, args.input, args.output_html, args.output_md)
        sys.exit(0)

    if args.pipeline:
        seed_doi = None
        seed_title = "Candidato Semilla"
        
        if args.seed_mode == "doi":
            if not args.doi:
                logger.error("Error: En '--seed-mode doi' se requiere especificar '--doi'.")
                sys.exit(1)
            seed_doi = args.doi.replace("https://doi.org/", "").strip()
            logger.info(f"[Etapa 1/5] Usando DOI semilla aportado por el usuario: {seed_doi}")
        else:
            if not args.search_query:
                logger.error("Error: En '--seed-mode search' se requiere especificar '--search-query'.")
                sys.exit(1)
                
            logger.info("\n" + "=" * 60)
            logger.info(f"   INICIANDO INVESTIGACIÓN AUTOMATIZADA DESDE CERO")
            logger.info(f"   Tema: '{args.search_query}' (Tema: {args.theme})")
            logger.info("=" * 60 + "\n")
            
            logger.info("[Etapa 1/5] Buscando artículo semilla en OpenAlex y PubMed...")
            
            pubmed_query = args.search_query
            if args.start_year and args.end_year:
                pubmed_query = f"{args.search_query} AND ({args.start_year}:{args.end_year}[DP])"
                logger.info(f"   [PubMed] Query refinada con fecha: '{pubmed_query}'")
                
            openalex_results = search_openalex_works(args.search_query, contact_email, verify_ssl=args.verify_ssl, count=30) or []
            pubmed_results = search_pubmed_works(pubmed_query, pubmed_key, count=30, verify_ssl=args.verify_ssl) or []
            
            results = []
            max_len = max(len(openalex_results), len(pubmed_results))
            for i in range(max_len):
                if i < len(openalex_results):
                    results.append(openalex_results[i])
                if i < len(pubmed_results):
                    results.append(pubmed_results[i])
                    
            if not results:
                logger.error("No se encontraron artículos semilla para el tema ingresado.")
                sys.exit(1)
                
            from .themes import get_theme
            theme_spec = get_theme(args.theme)
            precursor_keywords = theme_spec.get("precursor_keywords", [])

            valid_candidates = []
            for r in results:
                r_title = r.get("title", "")
                r_year = r.get("year") or r.get("publication_year")
                r_abstract = r.get("abstract", "")
                if validate_paper_criteria(r_title, r_abstract, r_year, start_year=args.start_year, end_year=args.end_year, precursor_filter=args.precursor_filter, precursor_keywords=precursor_keywords):
                    valid_candidates.append(r)
                    
            if not valid_candidates:
                logger.info("   [!] Ningún resultado directo cumple los criterios. Simplificando términos...")
                simple_query = args.search_query.replace(" AND ", " ").replace(" OR ", " ").replace("(", "").replace(")", "").replace('"', "").strip()
                openalex_results_s = search_openalex_works(simple_query, contact_email, verify_ssl=args.verify_ssl, count=30) or []
                pubmed_results_s = search_pubmed_works(simple_query, pubmed_key, count=30, verify_ssl=args.verify_ssl) or []
                results_s = []
                max_len_s = max(len(openalex_results_s), len(pubmed_results_s))
                for i in range(max_len_s):
                    if i < len(openalex_results_s):
                        results_s.append(openalex_results_s[i])
                    if i < len(pubmed_results_s):
                        results_s.append(pubmed_results_s[i])
                for r in results_s:
                    r_title = r.get("title", "")
                    r_year = r.get("year") or r.get("publication_year")
                    r_abstract = r.get("abstract", "")
                    if validate_paper_criteria(r_title, r_abstract, r_year, start_year=args.start_year, end_year=args.end_year, precursor_filter=args.precursor_filter, precursor_keywords=precursor_keywords):
                        valid_candidates.append(r)

            if valid_candidates:
                logger.info(f"   [+] Encontrados {len(valid_candidates)} candidatos semilla válidos.")
                seed_work = valid_candidates[0]
            else:
                logger.warning("   [!] Ningún candidato cumple los criterios estrictos de precursor. Relajando filtros...")
                for r in results:
                    r_title = r.get("title", "")
                    r_year = r.get("year") or r.get("publication_year")
                    r_abstract = r.get("abstract", "")
                    if validate_paper_criteria(r_title, r_abstract, r_year, start_year=args.start_year, end_year=args.end_year, precursor_filter=False):
                        valid_candidates.append(r)
                if valid_candidates:
                    seed_work = valid_candidates[0]
                else:
                    seed_work = None
                    for r in results:
                        if r.get("doi") and "pmid:" not in r.get("doi"):
                            seed_work = r
                            break
                    if not seed_work:
                        seed_work = results[0]
                
            seed_doi = (seed_work.get("doi") or "").replace("https://doi.org/", "")
            seed_title = seed_work.get("title", "Sin título")
            logger.info(f"   [+] Artículo semilla seleccionado:")
            logger.info(f"       Título: {seed_title}")
            logger.info(f"       DOI: {seed_doi}")
        
        pdf_dir = args.pdf_dir
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            output_html = os.path.join(args.output_dir, args.output_html or "red_investigacion.html")
            output_md = os.path.join(args.output_dir, args.output_md or "base_conocimiento.md")
            matrix_path = os.path.join(args.output_dir, args.output or "matriz_auditoria_automatizada.xlsx")
            r_cooccur_html = os.path.join(args.output_dir, "red_coocurrencia.html")
            r_biblio_md = os.path.join(args.output_dir, "base_bibliometria.md")
            r_report_html = os.path.join(args.output_dir, "reporte_editorial.html")
            if not pdf_dir:
                pdf_dir = os.path.join(args.output_dir, "documentos_temporales")
        else:
            output_html = args.output_html or "red_investigacion.html"
            output_md = args.output_md or "base_conocimiento.md"
            matrix_path = args.output or "matriz_auditoria_automatizada.xlsx"
            r_cooccur_html = "red_coocurrencia.html"
            r_biblio_md = "base_bibliometria.md"
            r_report_html = "reporte_editorial.html"
            
        logger.info("\n[Etapa 2/5] Ejecutando análisis de linaje científico en vivo...")
        max_refs = args.max_refs if args.max_refs > 0 else None
        
        nodes, edges = execute_live_lineage(
            doi=seed_doi,
            output_html=output_html,
            output_md=output_md,
            api_source=args.api_source,
            scopus_key=scopus_key,
            pubmed_key=pubmed_key,
            contact_email=contact_email,
            verbose=args.verbose,
            full_text=args.full_text,
            pdf_dir=pdf_dir,
            theme=args.theme,
            max_refs=max_refs,
            depth=args.depth,
            cache=cache,
            verify_ssl=args.verify_ssl,
            max_total_nodes=args.max_total_nodes,
            start_year=args.start_year,
            end_year=args.end_year,
            precursor_filter=args.precursor_filter
        )
        
        logger.info("\n[Etapa 3/5] Generando y poblando matriz de síntesis Excel...")
        generate_populated_matrix(nodes, matrix_path, args.theme)
        
        if rscript_path:
            logger.info("\n[Etapa 4/5] Ejecutando análisis R-Bibliometrix nativo...")
            ensure_r_packages(rscript_path)
            run_r_native_analysis(rscript_path, matrix_path, r_cooccur_html, r_biblio_md)
            
            logger.info("\n[Etapa 5/5] Compilando reporte R Markdown...")
            run_r_report(rscript_path, matrix_path, r_report_html)
            
            logger.info("\n" + "=" * 60)
            logger.info("   ¡PIPELINE AUTOMATIZADO FINALIZADO CON ÉXITO!")
            logger.info(f"   - Red de Linaje: {output_html}")
            logger.info(f"   - Base de Conocimiento: {output_md}")
            logger.info(f"   - Matriz Poblada Excel: {matrix_path}")
            logger.info(f"   - Red de Co-ocurrencias R: {r_cooccur_html}")
            logger.info(f"   - Reporte Editorial R Markdown: {r_report_html}")
            logger.info("=" * 60 + "\n")
        else:
            logger.warning("\n[Advertencia] Rscript no encontrado en el sistema. Se omiten etapas de R.")
            logger.info("\n" + "=" * 60)
            logger.info("   ¡PIPELINE PARCIAL AUTOMATIZADO FINALIZADO!")
            logger.info(f"   - Red de Linaje: {output_html}")
            logger.info(f"   - Base de Conocimiento: {output_md}")
            logger.info(f"   - Matriz Poblada Excel: {matrix_path}")
            logger.info("=" * 60 + "\n")
            
        sys.exit(0)

    if args.linaje:
        if not args.doi:
            logger.error("Error: Se requiere `--doi` para el motor de linaje.")
            sys.exit(1)

        max_refs = args.max_refs if args.max_refs > 0 else None

        execute_live_lineage(
            doi=args.doi,
            output_html=args.output_html,
            output_md=args.output_md,
            api_source=args.api_source,
            scopus_key=scopus_key,
            pubmed_key=pubmed_key,
            contact_email=contact_email,
            verbose=args.verbose,
            full_text=args.full_text,
            pdf_dir=args.pdf_dir,
            theme=args.theme,
            max_refs=max_refs,
            depth=args.depth,
            cache=cache,
            verify_ssl=args.verify_ssl,
            max_total_nodes=args.max_total_nodes,
            start_year=args.start_year,
            end_year=args.end_year,
            precursor_filter=args.precursor_filter
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
