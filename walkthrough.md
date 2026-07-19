# Walkthrough: Correcciones de Código y Manuscrito de SoftwareX

Este documento resume las refactorizaciones de código finalizadas con éxito y las actualizaciones en el manuscrito para su envío a la revista **SoftwareX** (Elsevier).

---

## 1. Mejoras en el Código (Software)

1.  **Conversión Automática de Mermaid a PNG (`matrix_generator.py` y `r_bridge.py`)**:
    *   Se implementó la función `render_mermaid_to_png(mermaid_code, output_png_path)` que consume la API de `mermaid.ink` mediante codificación en base64 de forma directa e independiente.
    *   Tanto el asistente interactivo PRISMA como la tubería cienciométrica principal en R-Bridge ahora guardan y renderizan de forma automatizada los archivos `diagrama_prisma.png` y `metodologia_prisma.png` / `metodologia_prisma.jpg` en el directorio de salida.
    *   Esto permite al usuario insertar de forma directa las imágenes físicas resultantes del diagrama de flujo PRISMA en su artículo de Word/LaTeX sin depender de intérpretes externos de Mermaid.

2.  **Motor Cualitativo Contextual Sin Duplicidades (`matrix_generator.py`)**:
    *   Se introdujo una heurística de coincidencia semántica por columna (analizando si la columna solicita población, diseño de estudio, variables o limitaciones) para extraer oraciones contextuales del abstract.
    *   Se implementó un control de unicidad de oraciones por fila (`used_sentences` set). Esto garantiza que las columnas de los 13 temas disciplinarios se pueblen con datos cualitativos ricos y diferenciados, **impidiendo de forma absoluta que la misma oración del abstract se repita en diferentes columnas del Excel**.

---

## 2. Actualización del Manuscrito Científico

*   **Ajuste y Corrección de Citas:**
    *   Se eliminó al competidor no publicado `Düzenli et al. (2026)` (manuscrito en proceso de revisión de código `SOFTX-D-26-00232` en GitHub) para evitar objeciones del comité editorial.
    *   Se corrigió la autoría de `ScopusLit` a `Arroyo (2026)` (un solo autor).
    *   Se corrigió la coautoría de `sprynger` a `Herrmann & Rose (2025)`.
*   **Fusión Comparativa en Sección 4:**
    *   La matriz y discusión comparativa cienciométrica completa frente a los competidores reales de *SoftwareX* (*ScopusLit*, *EmbedSLR*, *sprynger* y *BibexPy*) se inyectaron directamente en la **Sección 4 (Impact and Comparison)** del manuscrito principal.
*   **Referencia a Figuras:**
    *   Se actualizó la Sección 2.1 para sustituir los bloques de código Mermaid planos por llamadas a la imagen física `metodologia_prisma.png` generada automáticamente por el software.

---

## 3. Pruebas de Calidad Realizadas

1.  **Suite de Tests Unitarios:**
    *   Se ampliaron y corrieron con éxito absoluto los **39 tests unitarios** (`OK`), incluyendo pruebas específicas para el cálculo de calidad GRADE y aserciones del Markdown.
2.  **Verificación en Vivo (Carpeta `PRUEBASMEDICINA`, `PRUEBASINDUSTRIAL` y `PRUEBASBIO`):**
    *   Se re-ejecutaron los tres pipelines de control con éxito absoluto. 
    *   Se validó visualmente la creación de las imágenes PRISMA (`metodologia_prisma.png`, `metodologia_prisma.jpg`) en el subdirectorio de figuras.
    *   Se comprobó la diferenciación cualitativa correcta de columnas en el Excel poblado.
3.  **Sincronización en GitHub:**
    *   Se realizó commit y push final a la rama `main` del repositorio oficial: [Joax1213/SCRIPTMETODOLOGICO](https://github.com/Joax1213/SCRIPTMETODOLOGICO) en la revisión `2cf8064`.

---

## 4. Correcciones Específicas de Calidad (Sonnet 5 Audits)

Se implementaron y validaron 5 correcciones críticas y de contenido identificadas en la última fase:

1.  **Rigor de Calidad GRADE (Q-1 🔴 Crítico):**
    *   Se corrigió el regex `s|alta|fuerte` en `parse_quality_and_bias` que clasificaba cualquier celda con la letra "s" (como "Revisar en texto completo") como positiva.
    *   Ahora utiliza límites de palabra `\b` (ej. `\b(?:sí|alta|fuerte)\b`) y un set de exclusión explícita para evitar que los placeholders se cuenten en las estadísticas.
    *   Se resolvió la colisión de nombres de columnas en la matriz Excel (que causaba que "Resultados Estadísticos" se detectara en lugar de "Calidad del Estudio").
2.  **Preguntas de Investigación con Datos Reales (Q-2 🟠 Alto):**
    *   Las respuestas automáticas en la sección de RQs de `reporte_manuscrito.md` ahora se calculan dinámicamente.
    *   La RQ3 inyecta el número de artículos reales, el porcentaje de calidad GRADE de 3/3, el promedio de rigor y el porcentaje de artículos con riesgo de sesgo calculados directamente de los datos del corpus.
3.  **Refinamiento de Extracción en Medicina (A-5 🟠 Alto):**
    *   Se implementó un extractor semántico por regex para la columna "Intervención/Exposición" enfocado en el abstract y validando que no duplique accidentalmente el título.
    *   Se unificó el fallback de "Nivel de Evidencia (GRADE)" para usar "No reportado" en lugar del título completo.
4.  **Corte por Decimales (A-6 🟠 Alto):**
    *   Se corrigió el regex de extracción en `themes.py` reemplazando `[^.]{30,150}` por un lookahead negativo que evita cortar en puntos decimales (como `p=0.003` o `F1=0.89`), cortando únicamente en límites reales de oración.
5.  **Filtro de Stopwords en Visualizador Interactiva (N-1 🟡 Menor):**
    *   Se importó la lista compartida `STOP_WORDS` de `themes.py` en `visualizer.py` para evitar que palabras funcionales ("with", "from", "using") se nombren como ejes principales en la clasificación de clusters de la red.

---

## 5. Correcciones de Robustez y Auditoría Profunda (Nuevos Fallos)

Se implementaron y validaron 5 correcciones críticas adicionales encontradas en el escaneo de código profundo:

1.  **DOI Nulo en OpenAlex (🔴 Crítico — Estabilidad):**
    *   Se corrigió en [openalex_client.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/openalex_client.py#L80-92) para evitar caídas con `AttributeError` al intentar hacer `.replace()` sobre DOIs nulos devueltos por la API de OpenAlex.
    *   Ahora implementa un fallback seguro que utiliza el ID de OpenAlex del artículo (e.g. `W12345678`) si no se cuenta con DOI.
2.  **Lista de UIDs Vacía en PubMed (🔴 Crítico — Estabilidad):**
    *   Se corrigió en [pubmed_client.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/pubmed_client.py#L98) agregando un control defensivo antes de acceder al índice 0 de la lista de UIDs, previniendo excepciones de tipo `IndexError` en búsquedas que no arrojan resultados.
3.  **Inmunidad de Comillas en Reporte R (🟠 Alto — Estabilidad):**
    *   Se modificó [r_bridge.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/r_bridge.py#L580-770) para escribir el archivo de reporte `temp_report.Rmd` directamente desde Python a disco.
    *   Esto elimina la inyección de cadenas con comillas simples (`'`) contenidas en los abstracts dentro del script de R, evitando errores de sintaxis (`SyntaxError` en R) y previniendo caídas silenciosas hacia el Plotly fallback.
4.  **Omisión del Filtro de Precursores en Semilla (🟠 Alto — Lógica):**
    *   Se corrigió en [cli.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/cli.py#L341-367) cargando las palabras clave de precursores del tema seleccionado (`get_theme(args.theme)`) y pasándolas de forma explícita a `validate_paper_criteria` durante la selección del artículo semilla en la Etapa 1/5.
5.  **Fechas y Años Nulos en APIs (🔴 Crítico — Estabilidad):**
    *   Se implementó casteo seguro a string en el parseo de `prism:coverDate` de Scopus ([scopus_client.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/scopus_client.py#L130) y [lineage_engine.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/lineage_engine.py#L125)) y de `pubdate` de PubMed ([pubmed_client.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/pubmed_client.py#L112,206)).
    *   Esto evita caídas por `TypeError` o `AttributeError` ante artículos con metadatos de fecha nulos.
    *   Se corrigió también el cálculo de rango de años en [matrix_generator.py](file:///C:/Users/JOAQUIN/Documents/SCRIPMETODOLÓGICO/src/bibliometric_analyzer/matrix_generator.py#L659) mediante conversión coercitiva numérica para evitar comparaciones alfabéticas erróneas (ej: con valores `"N/A"`).

---

## 6. Ejecución de la Prueba Exhaustiva de Fin a Fin

Se ejecutó una prueba exhaustiva en vivo del pipeline cienciométrico completo utilizando el script de control [run_exhaustive_test.py](file:///C:/Users/JOAQUIN/.gemini/antigravity/brain/316b59cc-f20c-4170-babe-c8ea81f14564/scratch/run_exhaustive_test.py):

*   **Consulta Utilizada:** `"L-DOPA L-tyrosine vicia faba"` (Tema: `phytochemistry`, con `--precursor-filter`).
*   **Resultados de la Ejecución:**
    *   **Extracción y Cribado (Etapas 1-4):** Completados con éxito. Se validaron los filtros disciplinarios de precursor y se populó la matriz Excel de auditoría detallada.
    *   **Red Temática y Visualización:** Clasificación de ejes temática automática (`Eje 1: L-Dopa, L-Tyrosine...`) y generación exitosa del visor de red interactivo HTML (`red_coocurrencia.html`).
    *   **Compilación R Markdown (Etapa 5):** Renderización exitosa del archivo Rmd vía Rscript y Pandoc, generando el reporte editorial oficial en formato HTML sin errores sintácticos de comillas ([reporte_editorial.html](file:///C:/Users/JOAQUIN/Documents/Prueba4/levodopa_exhaustive_test/reporte_editorial.html)).
    *   **Código de salida de integración:** `0` (Éxito absoluto).

Todos los cambios fueron sincronizados y empujados exitosamente a GitHub (Commit [`3751bf2`](https://github.com/Joax1213/SCRIPTMETODOLOGICO)).

