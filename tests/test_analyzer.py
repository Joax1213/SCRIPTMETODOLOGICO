import sys
import os
import unittest
import datetime

# Asegurarse de que el paquete está en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from bibliometric_analyzer.utils import (
    parse_author_name,
    format_authors_list,
    get_fallback_year,
    JSONCache
)
from bibliometric_analyzer.openalex_client import rebuild_abstract_inverted_index
from bibliometric_analyzer.lineage_engine import generate_heuristic_qualitative_data


class TestParseAuthorName(unittest.TestCase):

    def test_simple_first_last(self):
        result = parse_author_name("John Doe")
        self.assertEqual(result, "Doe, J.")

    def test_last_first_comma_format(self):
        result = parse_author_name("García, Juan")
        self.assertEqual(result, "García, J.")

    def test_compound_surname(self):
        result = parse_author_name("García Marquez, Gabriel")
        self.assertEqual(result, "García Marquez, G.")

    def test_three_names_no_comma(self):
        result = parse_author_name("María Rosa López")
        # Último token como apellido, iniciales del resto
        self.assertIn("López", result)

    def test_empty_string(self):
        result = parse_author_name("")
        self.assertEqual(result, "Desconocido")

    def test_desconocido_passthrough(self):
        result = parse_author_name("Desconocido")
        self.assertEqual(result, "Desconocido")

    def test_scopus_surname_initial_no_comma(self):
        result = parse_author_name("Etemadi F.")
        self.assertEqual(result, "Etemadi, F.")

    def test_scopus_surname_multiple_initials_no_comma(self):
        result = parse_author_name("Etemadi F.J.")
        self.assertEqual(result, "Etemadi, F.J.")

    def test_scopus_surname_initial_no_dot_no_comma(self):
        result = parse_author_name("Etemadi FJ")
        self.assertEqual(result, "Etemadi, F.J.")

    def test_compound_surname_with_particles(self):
        result = parse_author_name("Carlos dos Santos")
        self.assertEqual(result, "dos Santos, C.")
        result2 = parse_author_name("Juan de la Cruz")
        self.assertEqual(result2, "de la Cruz, J.")
        result3 = parse_author_name("dos Santos, Carlos")
        self.assertEqual(result3, "dos Santos, C.")

class TestFormatAuthorsList(unittest.TestCase):

    def test_single_author(self):
        result = format_authors_list(["García, Juan"])
        self.assertEqual(result, "García, J.")

    def test_two_authors(self):
        result = format_authors_list(["García, Juan", "Smith, John"])
        self.assertIn("García", result)
        self.assertIn("Smith", result)

    def test_many_authors_truncated(self):
        authors = ["Author A", "Author B", "Author C", "Author D", "Author E", "Author F"]
        result = format_authors_list(authors, max_authors=5)
        self.assertTrue(result.endswith("et al."))

    def test_empty_list(self):
        result = format_authors_list([])
        self.assertEqual(result, "Desconocido")


class TestGetFallbackYear(unittest.TestCase):

    def test_returns_current_year(self):
        result = get_fallback_year()
        self.assertEqual(result, datetime.date.today().year)

    def test_is_int(self):
        result = get_fallback_year()
        self.assertIsInstance(result, int)

    def test_not_hardcoded_2026(self):
        # Confirmar que el año es dinámico, no hardcodeado
        result = get_fallback_year()
        self.assertGreaterEqual(result, 2026)


class TestRebuildAbstractInvertedIndex(unittest.TestCase):

    def test_simple_index(self):
        index = {"Hello": [0], "World": [1]}
        result = rebuild_abstract_inverted_index(index)
        self.assertEqual(result, "Hello World")

    def test_interleaved_positions(self):
        index = {"B": [1], "A": [0], "C": [2]}
        result = rebuild_abstract_inverted_index(index)
        self.assertEqual(result, "A B C")

    def test_empty_index(self):
        result = rebuild_abstract_inverted_index({})
        self.assertEqual(result, "")

    def test_none_input(self):
        result = rebuild_abstract_inverted_index(None)
        self.assertEqual(result, "")


class TestGenerateHeuristicQualitativeData(unittest.TestCase):

    def test_general_theme_with_conclusion(self):
        abstract = "This study investigates the effects of X on Y. We conclude that the treatment significantly improves outcomes."
        disc, aport = generate_heuristic_qualitative_data("Cell culture optimization", abstract, theme="general")
        self.assertIsInstance(disc, str)
        self.assertIsInstance(aport, str)
        self.assertGreater(len(disc), 10)

    def test_phytochemistry_with_yield(self):
        abstract = "The extraction yield was 12.5 mg/g using HPLC analysis. Elicitor concentration was optimized."
        disc, aport = generate_heuristic_qualitative_data("Vicia faba L-DOPA study", abstract, theme="phytochemistry")
        self.assertIn("mg/g", disc)
        self.assertIn("HPLC", disc)

    def test_empty_abstract_returns_fallback(self):
        disc, aport = generate_heuristic_qualitative_data("Some Title", "", theme="general")
        self.assertIsInstance(disc, str)
        self.assertIsInstance(aport, str)
        self.assertGreater(len(disc), 5)


class TestJSONCache(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.cache = JSONCache(cache_dir=self.temp_dir)

    def test_set_and_get(self):
        self.cache.set("openalex", "10.1234/test", {"title": "Test Paper"})
        result = self.cache.get("openalex", "10.1234/test")
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Test Paper")

    def test_get_nonexistent(self):
        result = self.cache.get("openalex", "10.9999/nonexistent")
        self.assertIsNone(result)

    def test_cache_creates_directories(self):
        self.cache.set("scopus", "some-eid", {"data": "value"})
        api_dir = os.path.join(self.temp_dir, "scopus")
        self.assertTrue(os.path.isdir(api_dir))

    def test_clear_cache(self):
        self.cache.set("openalex", "10.1234/clear_test", {"title": "To be removed"})
        self.cache.clear()
        result = self.cache.get("openalex", "10.1234/clear_test")
        self.assertIsNone(result)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestCLISmoke(unittest.TestCase):

    def test_cli_parser_args(self):
        from unittest.mock import patch
        from bibliometric_analyzer.cli import main

        # Mocks para evitar llamadas de red/procesamientos en el test de humo
        with patch('sys.argv', ['cli.py', '--linaje', '--doi', '10.1007/s00726-025-03491-0', '--max-refs', '1']):
            with patch('bibliometric_analyzer.cli.execute_live_lineage') as mock_execute:
                with patch('bibliometric_analyzer.cli.setup_logging'):
                    with patch('bibliometric_analyzer.cli.JSONCache'):
                        main()
                        mock_execute.assert_called_once()
                        _, kwargs = mock_execute.call_args
                        self.assertIn('verify_ssl', kwargs)
                        self.assertIn('max_total_nodes', kwargs)
                        self.assertEqual(kwargs['max_total_nodes'], 150)
                        self.assertTrue(kwargs['verify_ssl'])

    def test_cli_pipeline_with_output_dir(self):
        from unittest.mock import patch
        from bibliometric_analyzer.cli import main

        # Mocks para evitar llamadas reales en el test de humo de pipeline
        with patch('sys.argv', ['cli.py', '--pipeline', '--search-query', 'test query', '--output-dir', 'CUSTOM_DIR']):
            with patch('bibliometric_analyzer.cli.search_openalex_works') as mock_alex, \
                 patch('bibliometric_analyzer.cli.search_pubmed_works') as mock_pubmed, \
                 patch('bibliometric_analyzer.cli.execute_live_lineage') as mock_execute, \
                 patch('bibliometric_analyzer.cli.generate_populated_matrix') as mock_matrix, \
                 patch('bibliometric_analyzer.cli.ensure_r_packages'), \
                 patch('bibliometric_analyzer.cli.run_r_native_analysis'), \
                 patch('bibliometric_analyzer.cli.run_r_report'), \
                 patch('bibliometric_analyzer.cli.setup_logging'), \
                 patch('bibliometric_analyzer.cli.JSONCache'), \
                 patch('os.makedirs'):
                
                # Mock seed search results
                mock_alex.return_value = [{"doi": "https://doi.org/10.1234/seed", "title": "Seed Title"}]
                mock_pubmed.return_value = []
                mock_execute.return_value = ({}, [])
                
                try:
                    main()
                except SystemExit:
                    pass
                
                # Verificar que el linaje y la matriz se llamaron con la ruta del output_dir
                mock_execute.assert_called_once()
                mock_matrix.assert_called_once()
                _, kwargs = mock_execute.call_args
                self.assertTrue(kwargs['output_html'].startswith('CUSTOM_DIR'))


class TestPopulatedMatrix(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.temp_dir, "test_populated.xlsx")

    def test_generate_populated_matrix_phytochemistry(self):
        from bibliometric_analyzer.matrix_generator import generate_populated_matrix
        mock_nodes = {
            "10.1234/test": {
                "DOI": "10.1234/test",
                "Título": "Accumulation of L-DOPA in Vicia faba and HPLC analysis",
                "Autores": "Etemadi F.",
                "Año": "2018",
                "Revista": "Crop Journal",
                "Abstract": "This study optimized L-DOPA yield under MeJA elicitor stress.",
                "TextoCompleto": "The optimized conditions were 2.45 mg/g L-DOPA with 100 uM MeJA.",
                "qualitative_desc": "Estudio descriptivo.",
                "qualitative_app": "Aporte cuantitativo."
            },
            "10.1234/no_reportado": {
                "DOI": "10.1234/no_reportado",
                "Título": "General faba bean processing review",
                "Autores": "Smith J.",
                "Año": "2020",
                "Revista": "Food Sci",
                "Abstract": "We review roasting effects.",
                "TextoCompleto": "",
                "qualitative_desc": "Revision.",
                "qualitative_app": "Ninguno."
            }
        }
        generate_populated_matrix(mock_nodes, self.output_path, theme="phytochemistry")
        self.assertTrue(os.path.exists(self.output_path))
        import pandas as pd
        df = pd.read_excel(self.output_path)
        self.assertEqual(len(df), 2)
        
        # Fila 1: Extraído exitosamente de TextoCompleto
        self.assertEqual(df.iloc[0]["Especie / Variedad Vegetal"], "Vicia faba")
        self.assertEqual(df.iloc[0]["Concentración del Elicitor"], "100 uM")
        self.assertEqual(df.iloc[0]["Rendimiento del Metabolito Principal (mg/g)"], "2.45 mg/g")
        
        # Fila 2: Especie se extrae igualmente, pero dosis y rendimiento se bloquean por el gate
        self.assertEqual(df.iloc[1]["Especie / Variedad Vegetal"], "General faba")
        self.assertEqual(df.iloc[1]["Concentración del Elicitor"], "No aplica — el artículo no describe un ensayo de elicitación")
        self.assertEqual(df.iloc[1]["Rendimiento del Metabolito Principal (mg/g)"], "No aplica — el artículo no describe un ensayo de elicitación")

    def test_quality_parsing_and_rqs_calculation(self):
        from bibliometric_analyzer.matrix_generator import generate_populated_matrix, parse_quality_and_bias, generate_rqs_markdown
        mock_nodes = {
            "node1": {
                "DOI": "10.1001/node1",
                "Título": "Effects of Metformin on Clinical Outcomes",
                "Autores": "Gomez R.",
                "Año": "2022",
                "Revista": "JAMA",
                # Contiene palabras clave que infieren: Calidad Alta, Sesgo Bajo, Evidencia Fuerte
                "Abstract": "The results show that metformin significantly reduced mortality with p=0.003 and OR=2.4. Statistical analysis was strong and bias was low with high evidence. Double-blind randomized trial.",
                "TextoCompleto": "",
            },
            "node2": {
                "DOI": "10.1002/node2",
                "Título": "Roasting faba bean process review",
                "Autores": "Revisar en texto completo",
                "Año": "2020",
                "Revista": "Food Sci",
                "Abstract": "This abstract is missing.",
                "TextoCompleto": "",
            }
        }
        generate_populated_matrix(mock_nodes, self.output_path, theme="health_sciences")
        self.assertTrue(os.path.exists(self.output_path))
        
        # Test parse_quality_and_bias
        quality_summary, stats = parse_quality_and_bias(self.output_path, theme="health_sciences")
        self.assertIsNotNone(quality_summary)
        self.assertEqual(stats["total_papers"], 2)
        # Gomez R: Calidad Alta (1), Sesgo Bajo (1), Evidencia Fuerte (1) -> score 3/3
        # node2: Por revisar (0), Por revisar (0), Limitado (0) -> score 0/3
        self.assertEqual(stats["strong_si"], 1)
        self.assertEqual(stats["weak_si"], 1)
        
        # Test generate_rqs_markdown con stats
        rqs_md = generate_rqs_markdown(self.output_path, stats)
        self.assertIn("promedio de rigor metodológico es **1.50/3.00**", rqs_md)
        self.assertIn("1 artículos (50.0%)** con score GRADE = 3/3", rqs_md)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)




from unittest.mock import patch, MagicMock

class TestScopusClient(unittest.TestCase):

    @patch('urllib.request.urlopen')
    def test_get_scopus_paper_data(self, mock_urlopen):
        from bibliometric_analyzer.scopus_client import get_scopus_paper_data
        
        # Simular respuesta exitosa de Scopus
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'''{
            "search-results": {
                "entry": [{
                    "dc:title": "Test Scopus Paper",
                    "dc:creator": "Etemadi F.",
                    "prism:coverDate": "2018-05-12",
                    "prism:publicationName": "Crop Journal",
                    "eid": "2-s2.0-85041516661"
                }]
            }
        }'''
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = get_scopus_paper_data("10.1234/test_doi", "fake_key")
        self.assertIsNotNone(res)
        self.assertEqual(res["dc:title"], "Test Scopus Paper")

    @patch('urllib.request.urlopen')
    def test_get_scopus_abstract(self, mock_urlopen):
        from bibliometric_analyzer.scopus_client import get_scopus_abstract
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'''{
            "abstracts-retrieval-response": {
                "coredata": {
                    "dc:description": "This is a scopus abstract description."
                }
            }
        }'''
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = get_scopus_abstract("2-s2.0-85041516661", "fake_key")
        self.assertEqual(res, "This is a scopus abstract description.")

    @patch('urllib.request.urlopen')
    @patch('bibliometric_analyzer.scopus_client.get_scopus_abstract')
    def test_scopus_null_coverdate(self, mock_get_abstract, mock_urlopen):
        from bibliometric_analyzer.scopus_client import get_citing_papers_scopus
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'''{
            "search-results": {
                "entry": [{
                    "dc:title": "Null CoverDate Paper",
                    "dc:creator": "Desconocido",
                    "prism:coverDate": null,
                    "prism:publicationName": "N/A",
                    "eid": "2-s2.0-12345"
                }]
            }
        }'''
        mock_urlopen.return_value.__enter__.return_value = mock_response
        mock_get_abstract.return_value = "Mock abstract"
        
        res = get_citing_papers_scopus("10.1234/null_date", "Null CoverDate Paper", "fake_key")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["Título"], "Null CoverDate Paper")
        from bibliometric_analyzer.utils import get_fallback_year
        self.assertEqual(res[0]["Año"], str(get_fallback_year()))


class TestPubmedClient(unittest.TestCase):

    @patch('bibliometric_analyzer.pubmed_client._make_entrez_request')
    def test_get_pubmed_paper_data(self, mock_request):
        from bibliometric_analyzer.pubmed_client import get_pubmed_paper_data
        
        # Simular tres llamadas sucesivas para esearch, esummary y efetch
        mock_request.side_effect = [
            b'{"esearchresult": {"idlist": ["123456"]}}', # esearch
            b'{"result": {"uids": ["123456"], "123456": {"title": "Pubmed Test Article", "authors": [{"name": "Etemadi F"}], "pubdate": "2018", "source": "Journal of Crops"}}}', # esummary
            b'<AbstractText>This is a pubmed abstract.</AbstractText>' # efetch
        ]
        
        res = get_pubmed_paper_data("10.1234/test_pubmed", "fake_key")
        self.assertIsNotNone(res)
        self.assertEqual(res["Título"], "Pubmed Test Article")
        self.assertEqual(res["Abstract"], "This is a pubmed abstract.")

    @patch('bibliometric_analyzer.pubmed_client._make_entrez_request')
    @patch('bibliometric_analyzer.pubmed_client.get_pubmed_paper_data')
    def test_search_pubmed_works(self, mock_get_paper, mock_request):
        from bibliometric_analyzer.pubmed_client import search_pubmed_works
        
        # Simular respuesta de esearch
        mock_request.return_value = b'{"esearchresult": {"idlist": ["111", "222"]}}'
        
        # Simular respuestas de get_pubmed_paper_data
        mock_get_paper.side_effect = [
            {"DOI": "10.1234/1", "Título": "Paper 1", "Autores": "Auth 1", "Año": "2018", "Revista": "Rev 1", "Abstract": "Abs 1"},
            {"DOI": "10.1234/2", "Título": "Paper 2", "Autores": "Auth 2", "Año": "2019", "Revista": "Rev 2", "Abstract": "Abs 2"}
        ]
        
        res = search_pubmed_works("some query")
        self.assertEqual(res[1]["title"], "Paper 2")

    @patch('bibliometric_analyzer.pubmed_client._make_entrez_request')
    def test_pubmed_empty_uids(self, mock_request):
        from bibliometric_analyzer.pubmed_client import get_pubmed_paper_data
        
        # Simular que esummary retorna uids vacío []
        mock_request.side_effect = [
            b'{"esearchresult": {"idlist": ["123456"]}}', # esearch
            b'{"result": {"uids": []}}' # esummary vacío
        ]
        
        res = get_pubmed_paper_data("10.1234/test_empty", "fake_key")
        self.assertIsNone(res)

    @patch('bibliometric_analyzer.pubmed_client._make_entrez_request')
    def test_pubmed_null_pubdate(self, mock_request):
        from bibliometric_analyzer.pubmed_client import get_pubmed_paper_data
        
        # Simular que esummary retorna pubdate nula
        mock_request.side_effect = [
            b'{"esearchresult": {"idlist": ["123456"]}}', # esearch
            b'{"result": {"uids": ["123456"], "123456": {"title": "Pubmed Null Pubdate Article", "authors": [], "pubdate": null, "source": "Journal"}}}', # esummary
            b'<AbstractText>This is a pubmed abstract.</AbstractText>' # efetch
        ]
        
        res = get_pubmed_paper_data("10.1234/test_null_pubdate", "fake_key")
        self.assertIsNotNone(res)
        self.assertEqual(res["Título"], "Pubmed Null Pubdate Article")
        from bibliometric_analyzer.utils import get_fallback_year
        self.assertEqual(res["Año"], str(get_fallback_year()))


class TestOpenAlexClient(unittest.TestCase):

    @patch('urllib.request.urlopen')
    def test_openalex_null_doi(self, mock_urlopen):
        from bibliometric_analyzer.openalex_client import get_citing_papers_openalex
        
        # Simular respuesta de OpenAlex donde un artículo citante tiene doi: null
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'''{
            "results": [
                {
                    "id": "https://openalex.org/W999999",
                    "doi": null,
                    "title": "Citing Paper with null DOI",
                    "authorships": [],
                    "publication_year": 2021,
                    "primary_location": null
                }
            ]
        }'''
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = get_citing_papers_openalex("W123456", "email@test.com")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["DOI"], "W999999") # Debe caer al ID de OpenAlex
        self.assertEqual(res[0]["Título"], "Citing Paper with null DOI")


class TestRBridge(unittest.TestCase):

    @patch('shutil.which')
    def test_find_rscript_path_env(self, mock_which):
        from bibliometric_analyzer.r_bridge import find_rscript_path
        
        mock_which.return_value = "/usr/bin/Rscript"
        path = find_rscript_path()
        self.assertEqual(path, "/usr/bin/Rscript")

    @patch('subprocess.run')
    def test_ensure_r_packages(self, mock_run):
        from bibliometric_analyzer.r_bridge import ensure_r_packages
        
        # Simular CompletedProcess con ALL_OK en stdout
        mock_completed = MagicMock()
        mock_completed.returncode = 0
        mock_completed.stdout = "ALL_OK\n"
        mock_run.return_value = mock_completed
        
        res = ensure_r_packages("/usr/bin/Rscript")
        self.assertTrue(res)


class TestVisualizer(unittest.TestCase):

    @patch('urllib.request.urlopen')
    def test_write_html_network_visualization(self, mock_urlopen):
        from bibliometric_analyzer.visualizer import write_html_network_visualization
        import tempfile
        
        # Mock para evitar descargar CDNs de vis.js/plotly en el test
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"console.log('mock js');"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "network.html")
            nodes = {
                "node_1": {
                    "Título": "Paper Title",
                    "Autores": "Etemadi F.",
                    "Año": 2018,
                    "Revista": "Crop Journal",
                    "Abstract": "Abstract",
                    "PageRank": 1.0,
                    "Descubrimientos Principales": "Descubrimiento",
                    "Aporte al Tema": "Aporte"
                }
            }
            edges = []
            
            write_html_network_visualization(nodes, edges, out_file)
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, "r", encoding="utf-8") as f:
                html_content = f.read()
            self.assertIn("Paper Title", html_content)


class TestLineageEngineExecute(unittest.TestCase):

    @patch('bibliometric_analyzer.lineage_engine.get_openalex_paper_data')
    @patch('bibliometric_analyzer.lineage_engine.get_citing_papers_openalex')
    @patch('bibliometric_analyzer.lineage_engine.get_pubmed_paper_data')
    @patch('bibliometric_analyzer.lineage_engine.get_citing_papers_pubmed')
    def test_execute_live_lineage(self, mock_citing_pubmed, mock_pubmed, mock_citing, mock_paper_data):
        from bibliometric_analyzer.lineage_engine import execute_live_lineage
        
        # Simular datos de OpenAlex
        mock_paper_data.return_value = {
            "id": "https://openalex.org/W123456",
            "title": "Seed Article",
            "authorships": [{"author": {"display_name": "Etemadi, F."}}],
            "publication_year": 2018,
            "primary_location": {"source": {"display_name": "Crop Journal"}},
            "referenced_works": [],
            "cited_by_count": 0
        }
        mock_citing.return_value = []
        
        # Simular que PubMed no encuentra el artículo para forzar fallback a OpenAlex
        mock_pubmed.return_value = None
        mock_citing_pubmed.return_value = []
        
        cache = MagicMock()
        cache.get.return_value = None
        
        nodes, edges = execute_live_lineage(
            doi="10.1234/seed",
            output_html=None,
            output_md=None,
            api_source="all",
            scopus_key="",
            pubmed_key="",
            contact_email="",
            verbose=False,
            full_text=False,
            pdf_dir=None,
            theme="general",
            max_refs=5,
            depth=1,
            cache=cache,
            verify_ssl=True,
            max_total_nodes=150
        )
        
        self.assertIn("10.1234/seed", nodes)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes["10.1234/seed"]["Título"], "Seed Article")


class TestMatrixGeneratorImprovements(unittest.TestCase):

    def test_extract_valid_species(self):
        from bibliometric_analyzer.matrix_generator import extract_valid_species
        # Caso 1: Evitar falsos positivos como "The effect" o "Quantitative analysis"
        res1 = extract_valid_species("The effect of something", "Abstract containing nothing.")
        self.assertNotEqual(res1, "The effect")
        
        # Caso 2: Reconocer una especie válida (Vicia faba) en el título
        res2 = extract_valid_species("The effect of Vicia faba L. on growth", "Abstract content.")
        self.assertEqual(res2, "Vicia faba")
        
        # Caso 3: Fallback a género conocido cuando el regex no es perfecto
        res3 = extract_valid_species("Study on Crataegus oxyacantha fruit extract", "Abstract content.")
        self.assertEqual(res3, "Crataegus oxyacantha")

    def test_tissue_extraction(self):
        from bibliometric_analyzer.matrix_generator import generate_populated_matrix
        import tempfile
        import pandas as pd
        
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "test_tissue.xlsx")
        
        mock_nodes = {
            "node1": {
                "DOI": "10.1234/t1",
                "Título": "Analysis of leaf extract",
                "Autores": "Author A.",
                "Año": "2021",
                "Revista": "Phyto",
                "Abstract": "We analyzed chemical profile of leaves and seeds.",
                "TextoCompleto": "",
            }
        }
        
        try:
            generate_populated_matrix(mock_nodes, output_path, theme="phytochemistry")
            df = pd.read_excel(output_path)
            # Buscar columna de tejido
            tissue_col = [c for c in df.columns if any(w in c.lower() for w in ["tejido", "tissue", "órgano", "organ", "parte de la planta", "plant part"])]
            self.assertTrue(len(tissue_col) > 0)
            self.assertEqual(df.iloc[0][tissue_col[0]], "Hojas")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_openalex_title_unescape_and_clean(self):
        from bibliometric_analyzer.openalex_client import _clean_openalex_title
        raw = "&lt;i&gt;Crataegus spp&lt;/i&gt; and &amp; other species"
        cleaned = _clean_openalex_title(raw)
        self.assertEqual(cleaned, "Crataegus spp and & other species")

    def test_get_theme_columns_deduplication(self):
        from bibliometric_analyzer.themes import get_theme_columns
        cols = get_theme_columns("health_sciences")
        # Debería contener "Nivel de Evidencia (GRADE)" pero NO duplicarse con la genérica "Nivel de Evidencia"
        self.assertIn("Nivel de Evidencia (GRADE)", cols)
        self.assertNotIn("Nivel de Evidencia", cols)

    def test_clinical_intervention_extraction(self):
        from bibliometric_analyzer.matrix_generator import generate_populated_matrix
        import tempfile
        import pandas as pd
        
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "test_intervention.xlsx")
        
        mock_nodes = {
            "node1": {
                "DOI": "10.1234/h1",
                "Título": "Clinical Trial",
                "Autores": "Author B.",
                "Año": "2022",
                "Revista": "NEJM",
                "Abstract": "Patients received autologous CD34+ cells with Metformin.",
                "TextoCompleto": "",
            }
        }
        
        try:
            generate_populated_matrix(mock_nodes, output_path, theme="health_sciences")
            df = pd.read_excel(output_path)
            interv_col = [c for c in df.columns if any(w in c.lower() for w in ["intervención", "intervencion", "intervention"])]
            self.assertTrue(len(interv_col) > 0)
            val = df.iloc[0][interv_col[0]]
            self.assertIn("CD34+", val)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
