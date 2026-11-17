"""Relatório leve de uma imagem, sem reler o DICOM nem alterar as medições."""
import html
import math
import os
from pathlib import Path

from .avaliacao import image_quality


def _fmt(value, places=2):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return '—'
    return f'{value:.{places}f}' if math.isfinite(value) else '—'


def _chart(objects, field, title, ylabel):
    """SVG de pontos: ID espacial é identificador, não profundidade física."""
    width, height = 700, 290
    left, right, top, bottom = 68, 20, 32, 55
    plot_w, plot_h = width - left - right, height - top - bottom
    points = []
    for obj in objects:
        value = obj.get(field)
        try:
            value = float(value)
        except (ValueError, TypeError):
            continue
        if math.isfinite(value):
            points.append((int(obj['id']), value, bool(obj.get('quality_flags'))))
    if not points:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>Sem valores finitos para este gráfico.</p></section>'
    values = [value for _, value, _ in points]
    ymin, ymax = min(values), max(values)
    if ymin == ymax:
        pad = max(1.0, abs(ymin) * .05)
    else:
        pad = (ymax - ymin) * .09
    ymin -= pad; ymax += pad
    xmax = max(1, max(id_ for id_, _, _ in points))
    def xp(id_):
        return left + (id_ - 1) / max(1, xmax - 1) * plot_w
    def yp(value):
        return top + (ymax - value) / (ymax - ymin) * plot_h
    parts = [f'<section class="chart"><h3>{html.escape(title)}</h3>',
             f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" class="axis"/>',
             f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" class="axis"/>']
    for tick in range(5):
        y = top + plot_h * tick / 4
        val = ymax - (ymax-ymin) * tick / 4
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left+plot_w}" y2="{y:.2f}" class="grid"/>')
        parts.append(f'<text x="{left-8}" y="{y+4:.2f}" text-anchor="end">{_fmt(val, 1)}</text>')
    step = max(1, math.ceil(xmax / 12))
    for id_ in range(1, xmax+1, step):
        parts.append(f'<text x="{xp(id_):.2f}" y="{top+plot_h+19}" text-anchor="middle">{id_}</text>')
    for id_, value, flagged in points:
        klass = 'flagged' if flagged else 'point'
        parts.append(f'<circle cx="{xp(id_):.2f}" cy="{yp(value):.2f}" r="4.5" class="{klass}">'
                     f'<title>R{id_:03d}: {_fmt(value, 3)}'
                     f'{"; alerta heurístico" if flagged else ""}</title></circle>')
    parts.append(f'<text x="{left+plot_w/2:.2f}" y="{height-5}" text-anchor="middle">'
                 'ID espacial da região (não é profundidade física)</text>')
    parts.append(f'<text x="16" y="{top+plot_h/2:.2f}" transform="rotate(-90 16 {top+plot_h/2:.2f})" '
                 f'text-anchor="middle">{html.escape(ylabel)}</text></svg></section>')
    return ''.join(parts)


def escrever_relatorio(destino, dicom, objects, sensibilidade, imagem_path=None):
    """Salva quatro gráficos e tabela da execução já medida."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    name = html.escape(Path(dicom).name)
    flagged = sum(bool(obj.get('quality_flags')) for obj in objects)
    all_flagged = bool(objects) and flagged == len(objects)
    analysis_state = image_quality(objects)['estado'].replace('provisoria', 'provisória')
    charts = [
        _chart(objects, 'mean', 'Sinal bruto', 'Média dos pixels DICOM'),
        _chart(objects, 'corrected', 'Sinal corrigido experimental', 'S corrigido'),
        _chart(objects, 'rsr', 'Relação sinal-ruído (RSR)', 'S bruto / DP da ROI'),
        _chart(objects, 'rcr', 'Relação contraste-ruído (RCR)', '|S - fundo| / DP do fundo'),
    ]
    image_link = ''
    if imagem_path is not None:
        relative = os.path.relpath(Path(imagem_path).resolve(), destino.parent.resolve())
        image_link = f'<p><a href="{html.escape(relative, quote=True)}">Abrir imagem de contornos e máscaras</a></p>'
    rows = []
    for obj in objects:
        values = [obj['region_id'], str(obj['raw_rank']), str(obj['corrected_rank']),
                  _fmt(obj['area_px'], 0), _fmt(obj['mean']), _fmt(obj['std']),
                  _fmt(obj['background']), _fmt(obj['background_std']),
                  _fmt(obj['corrected']), _fmt(obj['rsr']), _fmt(obj['rcr']),
                  html.escape('; '.join(obj.get('quality_flags', [])) or '—')]
        klass = ' class="flag"' if obj.get('quality_flags') else ''
        rows.append(f'<tr{klass}>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr>')
    page = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório DICOM — {name}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1150px;margin:auto;padding:25px;color:#243746}}
h1,h2{{color:#164563}}.warning{{background:#fff2e8;padding:12px;border-left:4px solid #d45227}}
.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(490px,1fr));gap:14px}}
.chart{{border:1px solid #dbe4ea;border-radius:7px;padding:10px}}svg{{width:100%;height:auto}}
svg text{{font-size:12px;fill:#334}}svg .axis{{stroke:#435263;stroke-width:1.5}}
svg .grid{{stroke:#dce3e8;stroke-width:1}}svg .point{{fill:#126782}}
svg .flagged{{fill:white;stroke:#d45227;stroke-width:2}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{padding:6px;border-bottom:1px solid #dbe4ea;text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}th{{background:#eaf2f5}}tr.flag{{background:#fff2e8}}
</style></head><body><h1>Relatório individual — {name}</h1>
<p>Sensibilidade: {_fmt(sensibilidade, 2)} · Regiões detectadas: {len(objects)} ·
Regiões com alerta heurístico: {flagged} · Análise: {analysis_state}</p>{image_link}
<p>As regiões têm IDs espaciais por execução. Os gráficos não atribuem profundidade física.
Sinal bruto e ruído vêm dos pixels originais do DICOM. O fundo é medido em anel;
o sinal corrigido usa a mediana dos fundos locais e é uma adaptação experimental,
não a ROI 12 do TCC. RSR = S/σ da ROI; RCR = |S - fundo|/σ do fundo.</p>
{'<p class="warning">Todas as regiões têm alerta heurístico. As curvas não constituem medições confiáveis sem revisão.</p>' if all_flagged else ''}
{'<p class="warning">A maioria das regiões tem alerta heurístico. Revise a imagem antes de interpretar as medições.</p>' if analysis_state == 'inconclusiva' and not all_flagged and objects else ''}
{'<p class="warning">Nenhuma região foi detectada com estes parâmetros.</p>' if not objects else ''}
<h2>Gráficos</h2><p>Pontos laranja vazios indicam alertas heurísticos.</p>
<div class="charts">{''.join(charts)}</div><h2>Tabela de medições</h2>
<div class="scroll"><table><thead><tr><th>ID</th><th>Rank bruto</th><th>Rank corrigido</th>
<th>Área (px)</th><th>S bruto</th><th>DP ROI</th><th>Fundo</th><th>DP fundo</th>
<th>S corrigido</th><th>RSR</th><th>RCR</th><th>Alertas</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>'''
    destino.write_text(page, encoding='utf-8')
    return destino
