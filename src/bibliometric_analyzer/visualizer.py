import os
import re
import json
import logging
from .utils import parse_author_name, get_ssl_context
from .themes import CLUSTER_COLORS

logger = logging.getLogger("bibliometric_analyzer")

def auto_classify_axes(keywords_list):
    """Agrupa de forma dinámica palabras clave en clusters temáticos (ejes).
    
    Nombra cada cluster basado en las 3 palabras clave más frecuentes.
    Asigna un color de CLUSTER_COLORS de forma secuencial.
    """
    if not keywords_list:
        return {}, []
        
    freq = {}
    for kw in keywords_list:
        kw_lower = kw.lower().strip()
        if kw_lower and len(kw_lower) > 2:
            freq[kw_lower] = freq.get(kw_lower, 0) + 1
            
    if not freq:
        return {}, []
        
    sorted_kws = sorted(freq.items(), key=lambda x: -x[1])
    top_kws = [k for k, v in sorted_kws[:40]]
    
    n_clusters = min(max(2, len(top_kws) // 5), len(CLUSTER_COLORS))
    if n_clusters < 2:
        n_clusters = 2
        
    clusters = {}
    for i, kw in enumerate(top_kws):
        c_id = i % n_clusters
        if c_id not in clusters:
            clusters[c_id] = []
        clusters[c_id].append(kw)
        
    axis_map = {}
    axes_info = []
    
    for c_id in sorted(clusters.keys()):
        kws_in_cluster = clusters[c_id]
        top3 = [k.title() for k in kws_in_cluster[:3]]
        axis_name = f"Eje {c_id + 1}: {', '.join(top3)}"
        color = CLUSTER_COLORS[c_id % len(CLUSTER_COLORS)]
        
        for kw in kws_in_cluster:
            axis_map[kw] = {"axis": axis_name, "color": color}
            
        axes_info.append({
            "name": axis_name,
            "color": color,
            "keywords": kws_in_cluster,
            "description": f"Agrupación temática de investigaciones asociadas con: {', '.join(top3)}."
        })
        
    return axis_map, axes_info

def classify_node_by_keywords(title, axis_map, default_color="#888888", default_axis="Tema General"):
    """Determina a qué eje temático pertenece un paper según la concordancia de su título."""
    if not title or not axis_map:
        return default_color, default_axis
        
    title_lower = title.lower()
    best_match = None
    best_count = 0
    
    for kw, info in axis_map.items():
        if kw in title_lower:
            count = title_lower.count(kw)
            if count > best_count:
                best_count = count
                best_match = info
                
    if best_match:
        return best_match["color"], best_match["axis"]
    return default_color, default_axis

def write_html_network_visualization(nodes, edges, path, keywords_nodes=None, keywords_edges=None, verify_ssl=True, theme_name="general"):
    logger.info(f"[HTML] Generando visor interactivo HTML en: {path}")
    
    output_dir = os.path.dirname(path) if path else os.getcwd()
    figuras_dir = os.path.join(output_dir, "figuras")
    os.makedirs(figuras_dir, exist_ok=True)
    
    vis_local_path = os.path.join(figuras_dir, "vis-network.min.js")
    plotly_local_path = os.path.join(figuras_dir, "plotly.min.js")
    
    import urllib.request
    ctx = get_ssl_context(verify_ssl)

    if not os.path.exists(vis_local_path):
        try:
            logger.info("[HTML] Descargando vis-network.min.js para soporte local offline...")
            req = urllib.request.Request("https://unpkg.com/vis-network/standalone/umd/vis-network.min.js", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                with open(vis_local_path, "wb") as f_vis:
                    f_vis.write(r.read())
        except Exception as e:
            logger.warning(f"[HTML] Advertencia: No se pudo descargar vis-network.min.js: {e}")
            logger.warning("[HTML] Fallback: El visor HTML usará CDN remoto (unpkg.com) — requiere conexión a internet para funcionar.")
            
    if not os.path.exists(plotly_local_path):
        try:
            logger.info("[HTML] Descargando plotly.min.js para soporte local offline...")
            req = urllib.request.Request("https://cdn.plot.ly/plotly-2.24.1.min.js", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                with open(plotly_local_path, "wb") as f_plotly:
                    f_plotly.write(r.read())
        except Exception as e:
            logger.warning(f"[HTML] Advertencia: No se pudo descargar plotly.min.js: {e}")
            logger.warning("[HTML] Fallback: El visor HTML usará CDN remoto (cdn.plot.ly) — requiere conexión a internet para funcionar.")
            
    all_extracted_keywords = []
    
    stop_words = {
        "the", "and", "a", "of", "in", "to", "for", "with", "as", "by", "on", "at", "an", "is", "from", "that", "this", "are", "was", "were", "be", "or", "which", "between", "their", "its", "both", "more", "also", "after", "during", "some", "other", "about", "into", "than", "then", "them", "they", "we", "our", "us", "you", "your",
        "have", "has", "had", "been", "do", "does", "did", "can", "could", "would", "should", "will", "may", "might", "must", "used", "using", "showed", "shown", "found", "observed", "determined", "suggests", "reported", "concluded", "investigated", "evaluated", "compared", "performed", "conducted", "obtained", "presented", "described",
        "study", "analysis", "results", "effects", "effect", "conditions", "methods", "method", "paper", "article", "journal", "research", "data", "significantly", "based", "different", "well", "high", "low", "new", "content", "compounds", "production", "properties", "increased", "expression", "extraction", "concentration", "yield", "significant", "increase", "decrease", "higher", "lower", "acid", "activity", "levels", "level", "samples", "sample", "treatment", "treatments", "time", "rate", "comparison", "compared", "days", "hours", "parameters", "values", "value", "control", "controls", "conditions", "however", "therefore", "furthermore", "moreover", "although", "disponible", "abstract", "no", "si", "con", "para", "por", "del", "las", "los", "una", "uno", "este", "esta", "estos", "estas", "como", "entre", "under"
    }
    
    word_doc_mapping = {}
    for n_id, data in nodes.items():
        abstract_text = data.get("Abstract") or ""
        if "abstract no disponible" in abstract_text.lower():
            abstract_text = ""
        text = ((data.get("Título") or "") + " " + abstract_text).lower()
        text_clean = re.sub(r'[^a-z0-9\s-]', '', text)
        words = set(w for w in text_clean.split() if len(w) > 3 and w not in stop_words)
        
        for comp in ["machine learning", "deep learning", "artificial intelligence", "climate change", "public health", "supply chain", "quality control", "human resources", "customer satisfaction", "food safety", "renewable energy", "social media", "big data", "case study", "systematic review"]:
            if comp in text:
                words.add(comp)
                
        for w in words:
            if w not in word_doc_mapping:
                word_doc_mapping[w] = set()
            word_doc_mapping[w].add(n_id)
            all_extracted_keywords.append(w)
            
    axis_map, axes_info = auto_classify_axes(all_extracted_keywords)
    
    if not keywords_nodes:
        frequent_words = {w: docs for w, docs in word_doc_mapping.items() if len(docs) >= 2}
        if len(frequent_words) < 5:
            frequent_words = {w: docs for w, docs in word_doc_mapping.items() if len(docs) >= 1}
            
        top_words = sorted(frequent_words.keys(), key=lambda w: len(frequent_words[w]), reverse=True)[:15]
        
        keywords_nodes = []
        keywords_edges = []
        
        for idx, word in enumerate(top_words):
            docs_list = list(frequent_words[word])
            freq = len(docs_list)
            
            kw_info = axis_map.get(word, {"axis": "Tema General", "color": "#BC6C25"})
            eje = kw_info["axis"]
            color_bg = kw_info["color"]
            color_border = "#333333"
            
            linked_docs = []
            for d_id in docs_list[:5]:
                d_data = nodes.get(d_id)
                if d_data:
                    author_short = parse_author_name(d_data['Autores']).split(',')[0]
                    linked_docs.append({
                        "doi": d_id,
                        "label": f"{author_short} ({d_data['Año']})",
                        "title": d_data['Título']
                    })
                    
            explanation = f"Este concepto clave ('{word}') aparece en {freq} artículos de la auditoría actual de linaje, fundamentando las bases del tema."
            
            keywords_nodes.append({
                "id": f"word_{word}",
                "label": word.upper(),
                "size": 15 + (freq * 5),
                "color": {
                    "background": color_bg,
                    "border": color_border,
                    "highlight": {"background": "#E6B800", "border": color_border}
                },
                "font": {"color": "#FFFFFF", "size": 12, "face": "Courier New"},
                "shape": "box",
                "title": f"<b>Concepto:</b> {word.upper()}<br><b>Eje:</b> {eje}<br><b>Ocurrencia:</b> {freq} papers<br>",
                "linked_docs": linked_docs,
                "explanation": explanation
            })
            
        for i in range(len(top_words)):
            for j in range(i+1, len(top_words)):
                w1 = top_words[i]
                w2 = top_words[j]
                common_docs = frequent_words[w1].intersection(frequent_words[w2])
                if len(common_docs) >= 1:
                    keywords_edges.append({
                        "from": f"word_{w1}",
                        "to": f"word_{w2}",
                        "arrows": "",
                        "color": {"color": "#BBBBBB", "highlight": "#1B4332"},
                        "width": 1.0 + len(common_docs) * 0.8,
                        "title": f"Co-ocurrencia en {len(common_docs)} artículos"
                    })
                    
    in_degrees = {}
    ancestors_map = {}
    descendants_map = {}
    for source, target, rel in edges:
        in_degrees[target] = in_degrees.get(target, 0) + 1
        if source not in ancestors_map:
            ancestors_map[source] = []
        ancestors_map[source].append(target)
        if target not in descendants_map:
            descendants_map[target] = []
        descendants_map[target].append(source)
        
    prs = [d.get("PageRank", 0.0) for d in nodes.values()]
    prs_sorted = sorted(prs)
    threshold_pr = prs_sorted[int(len(prs_sorted) * 0.85)] if prs_sorted else 0.05

    js_nodes = []
    for n_id, data in nodes.items():
        pr = data.get("PageRank", 0.05)
        size = 15 + (pr * 380)
        
        color_bg, eje_nombre = classify_node_by_keywords(data['Título'], axis_map, default_color="#BC6C25", default_axis="Tema General")
        color_border = "#333333"
        font_color = "#FFFFFF"
        
        is_authority = pr >= threshold_pr and pr > min(prs) and in_degrees.get(n_id, 0) > 0
        if is_authority:
            border_width = 4
            color_border_highlight = "#D90429"
            label = f"★ {data['Autores'].split(',')[0].upper()} ({data['Año']})"
            shadow_opt = {"enabled": True, "color": "rgba(217,4,41,0.5)", "size": 10, "x": 0, "y": 0}
        else:
            border_width = 1.5
            color_border_highlight = color_border
            label = f"{data['Autores'].split(',')[0]} ({data['Año']})"
            shadow_opt = {"enabled": True, "color": "rgba(0,0,0,0.15)", "size": 5, "x": 1, "y": 1}
            
        color_opt = {
            "background": color_bg,
            "border": color_border_highlight if is_authority else color_border,
            "highlight": {"background": "#E6B800" if is_authority else "#40916C", "border": "#D90429" if is_authority else color_border}
        }

        anc_list = []
        for anc_id in ancestors_map.get(n_id, []):
            anc_data = nodes.get(anc_id)
            if anc_data:
                anc_author = anc_data['Autores'].split(',')[0] if ',' in anc_data['Autores'] else anc_data['Autores']
                anc_list.append({"id": anc_id, "label": f"{anc_author} ({anc_data['Año']})", "title": anc_data['Título']})
                
        desc_list = []
        for desc_id in descendants_map.get(n_id, []):
            desc_data = nodes.get(desc_id)
            if desc_data:
                desc_author = desc_data['Autores'].split(',')[0] if ',' in desc_data['Autores'] else desc_data['Autores']
                desc_list.append({"id": desc_id, "label": f"{desc_author} ({desc_data['Año']})", "title": desc_data['Título']})

        title_tooltip = (
            f"<b>Título:</b> {data['Título']}<br>"
            f"<b>Autores:</b> {data['Autores']}<br>"
            f"<b>Revista:</b> {data['Revista']} ({data['Año']})<br>"
            f"<b>Eje Temático:</b> {eje_nombre}<br>"
            f"<b>PageRank:</b> {pr:.4f}<br><br>"
            f"<b>Descubrimientos:</b> {data['Descubrimientos Principales']}<br>"
            f"<b>Aporte:</b> {data['Aporte al Tema']}<br><br>"
            f"<i>*Haz doble clic para abrir el DOI original</i>"
        ).replace('"', '&quot;').replace('\n', ' ')
        
        js_nodes.append({
            "id": n_id,
            "label": label,
            "size": size,
            "title": title_tooltip,
            "color": color_opt,
            "font": {"color": "#FFFFFF" if font_color == "#FFFFFF" and not is_authority else ("#000000" if not is_authority else "#D90429"), "size": 11 if not is_authority else 13, "face": "Courier New", "bold": is_authority},
            "shape": "circle",
            "borderWidth": border_width,
            "shadow": shadow_opt,
            "full_title": data['Título'],
            "full_authors": data['Autores'],
            "full_journal": data['Revista'],
            "full_year": str(data['Año']),
            "full_abstract": data['Abstract'],
            "full_discoveries": data['Descubrimientos Principales'],
            "full_aporte": data['Aporte al Tema'],
            "eje_tematico": eje_nombre,
            "linked_ancestors": anc_list,
            "linked_descendants": desc_list
        })
        
    js_edges = []
    for source, target, rel in edges:
        js_edges.append({
            "from": source,
            "to": target,
            "arrows": "to",
            "color": {"color": "#888888", "highlight": "#1B4332"},
            "width": 1.5,
            "smooth": {"type": "cubicBezier", "roundness": 0.5}
        })
        
    years_dict = {}
    for n in nodes.values():
        yr = str(n.get("Año"))
        if yr.isdigit():
            years_dict[yr] = years_dict.get(yr, 0) + 1
            
    sorted_years = sorted(years_dict.keys())
    years_counts = [years_dict[y] for y in sorted_years]

    legend_html = ""
    for info in axes_info:
        legend_html += f"""
        <div class="legend-item" style="flex-direction: column; align-items: flex-start; margin-bottom: 8px;">
            <div style="display: flex; align-items: center;">
                <div class="legend-color" style="background-color: {info['color']};"></div>
                <span style="font-weight: bold; color: {info['color']};">{info['name']}</span>
            </div>
            <span style="font-size: 9.5px; color: #555; margin-left: 20px; line-height: 1.2;">{info['description']}</span>
        </div>
        """
    legend_html += """
    <div class="legend-item" style="margin-top: 8px; border-top: 1px solid #DDD; padding-top: 5px; flex-direction: column; align-items: flex-start;">
        <div style="display: flex; align-items: center;">
            <div class="legend-color" style="background-color: #FFF; border: 2px solid #D90429; border-radius: 0%; width: 10px; height: 10px;"></div>
            <span style="font-weight: bold; color: #D90429;">★ Autoridad Científica (Alto PageRank)</span>
        </div>
        <span style="font-size: 9.5px; color: #555; margin-left: 20px; line-height: 1.2;">Nodos clave con altos niveles de citación local y centralidad en la red de linaje.</span>
    </div>
    """

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Visor de Linaje Científico Interactivo</title>
    <script type="text/javascript" src="figuras/vis-network.min.js"></script>
    <script type="text/javascript">
        if (typeof vis === 'undefined') {{
            document.write('<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"><\\/script>');
        }}
    </script>
    <script src="figuras/plotly.min.js"></script>
    <script type="text/javascript">
        if (typeof Plotly === 'undefined') {{
            document.write('<script src="https://cdn.plot.ly/plotly-2.24.1.min.js"><\\/script>');
        }}
    </script>
    <style type="text/css">
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #F8F9FA;
            color: #333;
            display: flex;
            height: 100vh;
            overflow: hidden;
        }}
        #sidebar {{
            width: 380px;
            background-color: #FFFFFF;
            border-right: 1px solid #E0E0E0;
            display: flex;
            flex-direction: column;
            box-shadow: 2px 0 10px rgba(0,0,0,0.05);
            z-index: 10;
        }}
        #main {{
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            position: relative;
        }}
        #network-container {{
            flex-grow: 1;
            height: 70%;
            background-color: #FAFAFA;
            position: relative;
        }}
        #chart-container {{
            height: 30%;
            border-top: 1px solid #E0E0E0;
            background-color: #FFFFFF;
        }}
        .header {{
            padding: 20px;
            background-color: #1B4332;
            color: #FFFFFF;
        }}
        .header h1 {{
            font-size: 16px;
            margin: 0 0 5px 0;
            letter-spacing: 0.5px;
        }}
        .header p {{
            font-size: 11px;
            margin: 0;
            opacity: 0.8;
        }}
        .tab-btn {{
            flex: 1;
            padding: 12px;
            border: none;
            background: #F4F7F6;
            cursor: pointer;
            font-weight: bold;
            font-size: 11px;
            outline: none;
            color: #666;
            transition: all 0.3s;
            border-bottom: 2px solid transparent;
        }}
        .tab-btn.active {{
            background: #FFFFFF;
            border-bottom: 2px solid #1B4332;
            color: #1B4332;
        }}
        .tab-btn:hover {{
            background: #EAEAEA;
        }}
        .search-box {{
            padding: 15px;
            border-bottom: 1px solid #F0F0F0;
        }}
        .search-box input {{
            width: 90%;
            padding: 8px 12px;
            border: 1px solid #CCCCCC;
            border-radius: 4px;
            font-size: 13px;
            outline: none;
        }}
        #details {{
            padding: 20px;
            overflow-y: auto;
            flex-grow: 1;
            font-size: 13px;
            line-height: 1.5;
        }}
        #details h3 {{
            margin-top: 0;
            font-size: 14px;
            color: #1B4332;
            border-bottom: 1px solid #EEEEEE;
            padding-bottom: 5px;
            padding-top: 5px;
        }}
        .detail-item {{
            margin-bottom: 15px;
        }}
        .detail-label {{
            font-weight: bold;
            color: #666666;
            font-size: 11px;
            text-transform: uppercase;
        }}
        .detail-val {{
            margin-top: 2px;
        }}
        .legend {{
            position: absolute;
            top: 10px;
            left: 10px;
            background-color: rgba(255,255,255,0.95);
            border: 1px solid #CCCCCC;
            padding: 12px;
            border-radius: 6px;
            font-size: 11px;
            z-index: 5;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            max-width: 320px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 5px;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <div id="sidebar">
        <div class="header">
            <h1>AUDITORÍA Y LINAJE DE PAPERS</h1>
            <p>Análisis Cienciométrico Interactivo · {theme_name.upper()}</p>
        </div>
        <div style="display:flex; border-bottom:1px solid #E0E0E0;">
            <button id="btn-docs" class="tab-btn active" onclick="switchNetwork('docs')">Red Documental (Citas)</button>
            <button id="btn-keys" class="tab-btn" onclick="switchNetwork('keys')">Red Temática (Conceptos)</button>
        </div>
        <div class="search-box">
            <input type="text" id="search-input" placeholder="Buscar por título o autor..." oninput="filterNetwork()">
        </div>
        <div id="details">
            <h3>Detalle Seleccionado</h3>
            <p style="color:#888; font-style:italic;">Haz clic en un nodo de la red activa para visualizar su información detallada aquí.</p>
        </div>
    </div>
    
    <div id="main" style="position: relative;">
        <div id="network-container"></div>
        <div class="legend">
            {legend_html}
        </div>
        <div id="chart-container"></div>
    </div>

    <script type="text/javascript">
        const nodesDocsData = {json.dumps(js_nodes, ensure_ascii=False)};
        const edgesDocsData = {json.dumps(js_edges, ensure_ascii=False)};
        const nodesKeysData = {json.dumps(keywords_nodes or [], ensure_ascii=False)};
        const edgesKeysData = {json.dumps(keywords_edges or [], ensure_ascii=False)};
        
        let activeNetworkType = 'docs';
        let nodes = new vis.DataSet(nodesDocsData);
        let edges = new vis.DataSet(edgesDocsData);
        
        const container = document.getElementById('network-container');
        let data = {{ nodes: nodes, edges: edges }};
        const options = {{
            nodes: {{
                font: {{ face: 'Courier New' }}
            }},
            physics: {{
                forceAtlas2Based: {{
                    gravitationalConstant: -180,
                    centralGravity: 0.005,
                    springLength: 140,
                    springConstant: 0.08,
                    avoidOverlap: 1.0
                }},
                solver: 'forceAtlas2Based',
                stabilization: {{ iterations: 200 }}
            }}
        }};
        
        let network = new vis.Network(container, data, options);
        
        function switchNetwork(type) {{
            activeNetworkType = type;
            document.getElementById('btn-docs').classList.toggle('active', type === 'docs');
            document.getElementById('btn-keys').classList.toggle('active', type === 'keys');
            
            let nodesDataset, edgesDataset;
            if (type === 'docs') {{
                nodesDataset = new vis.DataSet(nodesDocsData);
                edgesDataset = new vis.DataSet(edgesDocsData);
                document.getElementById('search-input').placeholder = "Buscar por título o autor...";
            }} else {{
                nodesDataset = new vis.DataSet(nodesKeysData);
                edgesDataset = new vis.DataSet(edgesKeysData);
                document.getElementById('search-input').placeholder = "Buscar concepto temático...";
            }}
            
            data = {{ nodes: nodesDataset, edges: edgesDataset }};
            network.setData(data);
            
            document.getElementById('details').innerHTML = `
                <h3>Detalle Seleccionado</h3>
                <p style="color:#888; font-style:italic;">Haz clic en un nodo de la red activa para visualizar su información detallada aquí.</p>
            `;
            
            network.off("click");
            network.on("click", function (params) {{
                if (params.nodes.length > 0) {{
                    const nodeId = params.nodes[0];
                    const node = nodesDataset.get(nodeId);
                    showDetails(node);
                }}
            }});
        }}
        
        network.on("click", function (params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const node = nodes.get(nodeId);
                showDetails(node);
            }}
        }});
        
        network.on("doubleClick", function (params) {{
            if (activeNetworkType === 'docs' && params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                if (nodeId && !nodeId.startsWith('work_')) {{
                    window.open('https://doi.org/' + nodeId, '_blank');
                }}
            }}
        }});
        
        function selectNodeById(nodeId) {{
            network.selectNodes([nodeId]);
            const node = network.body.nodes[nodeId];
            if (node) {{
                network.focus(nodeId, {{
                    scale: 1.15,
                    animation: {{
                        duration: 800,
                        easingFunction: 'easeInOutQuad'
                    }}
                }});
                let activeDataset = (activeNetworkType === 'docs') ? nodes : new vis.DataSet(nodesKeysData);
                const dataNode = activeDataset.get(nodeId);
                if (dataNode) {{
                    showDetails(dataNode);
                }}
            }}
        }}
        
        function showDetails(node) {{
            const detailsDiv = document.getElementById('details');
            if (activeNetworkType === 'docs') {{
                let ancestorsHtml = '<p style="color:#888; font-style:italic; font-size:11px; margin:2px 0;">Ninguno en la red local.</p>';
                if (node.linked_ancestors && node.linked_ancestors.length > 0) {{
                    ancestorsHtml = '<ul style="padding-left:15px; margin:5px 0; font-size:12px; line-height:1.4;">';
                    node.linked_ancestors.forEach(anc => {{
                        ancestorsHtml += `<li>Cita a: <a href="#" onclick="selectNodeById('${{anc.id}}'); return false;" style="font-weight:bold; color:#028090; text-decoration:none;">${{anc.label}}</a> · <span style="color:#666; font-size:11px;">${{anc.title}}</span></li>`;
                    }});
                    ancestorsHtml += '</ul>';
                }}
                
                let descendantsHtml = '<p style="color:#888; font-style:italic; font-size:11px; margin:2px 0;">Ninguno en la red local.</p>';
                if (node.linked_descendants && node.linked_descendants.length > 0) {{
                    descendantsHtml = '<ul style="padding-left:15px; margin:5px 0; font-size:12px; line-height:1.4;">';
                    node.linked_descendants.forEach(desc => {{
                        descendantsHtml += `<li>Citado por: <a href="#" onclick="selectNodeById('${{desc.id}}'); return false;" style="font-weight:bold; color:#05668D; text-decoration:none;">${{desc.label}}</a> · <span style="color:#666; font-size:11px;">${{desc.title}}</span></li>`;
                    }});
                    descendantsHtml += '</ul>';
                }}

                detailsDiv.innerHTML = `
                    <h3>${{node.label}}</h3>
                    <div class="detail-item">
                        <div class="detail-label">Título</div>
                        <div class="detail-val" style="font-weight:bold; color:#1B4332;">${{node.full_title}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Autores</div>
                        <div class="detail-val">${{node.full_authors}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Revista / Fuente</div>
                        <div class="detail-val">${{node.full_journal}} (${{node.full_year}})</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">DOI</div>
                        <div class="detail-val"><a href="https://doi.org/${{node.id}}" target="_blank">${{node.id}}</a></div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Abstract</div>
                        <div class="detail-val" style="font-size:12px; max-height:150px; overflow-y:auto; border:1px solid #F0F0F0; padding:5px; background:#FAFAFA;">${{node.full_abstract}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Descubrimientos Clave</div>
                        <div class="detail-val" style="color:#3A5A40; font-style:italic;">${{node.full_discoveries}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Aporte al Tema</div>
                        <div class="detail-val" style="font-weight:600; color:#05668D;">${{node.full_aporte}}</div>
                    </div>
                    <div class="detail-item" style="border-top:1px solid #EEE; padding-top:10px; margin-top:10px;">
                        <div class="detail-label" style="color:#A0522D;">Ancestros del Linaje (Fundamento teórico)</div>
                        <div class="detail-val">${{ancestorsHtml}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label" style="color:#4682B4;">Descendientes del Linaje (Citas hacia adelante)</div>
                        <div class="detail-val">${{descendantsHtml}}</div>
                    </div>
                `;
            }} else {{
                let eje = "General / No clasificado";
                let pr = "0.05";
                if (node.title) {{
                    const ejePart = node.title.split('<b>Eje:</b> ');
                    if (ejePart.length > 1) eje = ejePart[1].split('<br>')[0];
                    const prPart = node.title.split('<b>Ocurrencia:</b> ');
                    if (prPart.length > 1) pr = prPart[1].split('<br>')[0];
                }}
                
                let docsHtml = '<p style="color:#888; font-style:italic; font-size:11px;">Ninguno identificado directamente.</p>';
                if (node.linked_docs && node.linked_docs.length > 0) {{
                    docsHtml = '<ul style="padding-left:15px; margin:5px 0; font-size:12px; line-height:1.4;">';
                    node.linked_docs.forEach(doc => {{
                        docsHtml += `<li><a href="https://doi.org/${{doc.doi}}" target="_blank" style="font-weight:bold; color:#028090; text-decoration:none;">${{doc.label}}</a>: ${{doc.title}}</li>`;
                    }});
                    docsHtml += '</ul>';
                }}
                
                let expl = node.explanation || "Este nodo representa un término o concepto de alta ocurrencia.";
                
                detailsDiv.innerHTML = `
                    <h3>Concepto: ${{node.label}}</h3>
                    <div class="detail-item">
                        <div class="detail-label">Eje Temático</div>
                        <div class="detail-val" style="font-weight:bold; color:#1B4332;">${{eje}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Centralidad (Ocurrencia)</div>
                        <div class="detail-val" style="font-family:monospace; font-weight:bold; color:#D90429;">${{pr}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Relevancia y Contribución al Tema</div>
                        <div class="detail-val" style="font-size:12px; line-height:1.4; color:#3A5A40; font-style:italic;">${{expl}}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Evidencia Científica en la Auditoría</div>
                        <div class="detail-val">${{docsHtml}}</div>
                    </div>
                `;
            }}
        }}
        
        function filterNetwork() {{
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            const currentNodes = network.body.data.nodes;
            
            if (query === "") {{
                currentNodes.forEach(n => {{
                    currentNodes.update({{ id: n.id, opacity: 1.0 }});
                }});
            }} else {{
                currentNodes.forEach(n => {{
                    let match = false;
                    if (activeNetworkType === 'docs') {{
                        match = (n.full_title && n.full_title.toLowerCase().includes(query)) || 
                                (n.full_authors && n.full_authors.toLowerCase().includes(query));
                    }} else {{
                        match = n.label && n.label.toLowerCase().includes(query);
                    }}
                    currentNodes.update({{ id: n.id, opacity: match ? 1.0 : 0.15 }});
                }});
            }}
        }}

        const chartData = [{{
            x: {json.dumps(sorted_years)},
            y: {json.dumps(years_counts)},
            type: 'bar',
            marker: {{ color: '#2D6A4F' }}
        }}];
        
        const chartLayout = {{
            title: 'Producción Científica del Grafo por Año',
            font: {{ size: 10 }},
            margin: {{ t: 30, b: 30, l: 30, r: 10 }},
            height: 180,
            autosize: true
        }};
        
        Plotly.newPlot('chart-container', chartData, chartLayout, {{displayModeBar: false}});
    </script>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_template)
    logger.info(f"Visor HTML interactivo empaquetado en: {path}")
