"""Recria figuras quantitativas do TCC a partir de um lote já processado.

As abscissas são IDs espaciais, NÃO profundidades físicas. Correspondências
entre imagens são provisórias e usam apenas distância entre centroides.
"""
import argparse
import csv
import html
import json
import math
import os
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault('MPLCONFIGDIR', '/tmp/radio2_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pydicom


EXPOSURES = [
    ('Mão46_1', 'Mão', 46, 1), ('Mão46_2', 'Mão', 46, 2),
    ('Mão46_4', 'Mão', 46, 4), ('Crânio81_1', 'Crânio', 81, 1),
    ('Crânio81_2', 'Crânio', 81, 2), ('Crânio81_4', 'Crânio', 81, 4),
    ('Tórax125_1', 'Tórax', 125, 1), ('Tórax125_2', 'Tórax', 125, 2),
    ('Tórax125_4', 'Tórax', 125, 4),
]
INVALID = {'Tórax125_2': 'candidatos extensos/espúrios',
           'Tórax125_4': 'somente um candidato de baixo contraste'}
FIELDS = ['sinal_bruto', 'desvio_padrao_roi', 'fundo_local',
          'desvio_padrao_fundo', 'sinal_corrigido', 'rsr', 'rcr']
PT = {'sinal_bruto': 'Sinal bruto (níveis DICOM)',
      'sinal_corrigido': 'Sinal corrigido experimental',
      'rsr': 'RSR = S / σ ROI', 'rcr': 'RCR = |S - fundo| / σ fundo'}


def finite(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return float('nan')
    return result if math.isfinite(result) else float('nan')


def load_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    required = set(FIELDS + ['region_id', 'centro_x_imagem_px',
                             'centro_y_imagem_px', 'area_px', 'alertas'])
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f'CSV ausente, vazio ou com colunas faltando: {path}')
    for row in rows:
        for key in FIELDS + ['centro_x_imagem_px', 'centro_y_imagem_px', 'area_px']:
            row[key] = finite(row[key])
        row['id_num'] = int(row['region_id'][1:])
        # Confere as equações no dado exportado antes de reutilizá-lo.
        s, sd, b, bd = (row[k] for k in ('sinal_bruto', 'desvio_padrao_roi',
                                        'fundo_local', 'desvio_padrao_fundo'))
        expected_rsr = s / sd if sd > 0 else float('nan')
        expected_rcr = abs(s - b) / bd if bd > 0 else float('nan')
        for name, expected in [('rsr', expected_rsr), ('rcr', expected_rcr)]:
            if math.isfinite(expected) and not math.isclose(row[name], expected,
                                                             rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError(f'{path}: {row["region_id"]} {name} diverge da fórmula')
    return sorted(rows, key=lambda row: row['id_num'])


def match(reference, target, max_distance=35.0):
    """Associação espacial única por menor distância, sem inferir profundidade."""
    candidates = []
    for a in reference:
        for b in target:
            distance = math.hypot(a['centro_x_imagem_px'] - b['centro_x_imagem_px'],
                                  a['centro_y_imagem_px'] - b['centro_y_imagem_px'])
            if distance <= max_distance:
                candidates.append((distance, a['id_num'], b['id_num'], b))
    used_a, used_b, pairs = set(), set(), {}
    for distance, aid, bid, row in sorted(candidates):
        if aid not in used_a and bid not in used_b:
            used_a.add(aid); used_b.add(bid)
            pairs[aid] = (row, distance)
    return pairs


def setup_ax(ax, title, ylabel, xmax=24):
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('ID espacial da região de referência (sem profundidade atribuída)')
    ax.set_ylabel(ylabel)
    ax.set_xlim(0.5, max(24.5, xmax + 0.5))
    ax.set_xticks(range(1, max(25, xmax + 1), 2))
    ax.grid(alpha=.22)


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches='tight')
    plt.close(fig)


def plot_single(data, name, number, out):
    rows = data[name]['rows']
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharex=True)
    for ax, key, part in zip(axes, ('sinal_bruto', 'sinal_corrigido'), ('A', 'B')):
        good = [r for r in rows if not r['alertas'] and math.isfinite(r[key])]
        flagged = [r for r in rows if r['alertas'] and math.isfinite(r[key])]
        ax.scatter([r['id_num'] for r in good], [r[key] for r in good],
                   color='#126782', s=26, label='sem alerta')
        ax.scatter([r['id_num'] for r in flagged], [r[key] for r in flagged],
                   facecolors='none', edgecolors='#d45227', s=48,
                   label='com alerta heurístico')
        setup_ax(ax, f'{part}. {PT[key]}', PT[key], len(rows))
        ax.legend(fontsize=8)
    fig.suptitle(f'Figura {number} (análoga) | {name} | {len(rows)} candidatos')
    save(fig, out)


def plot_comparison(data, technique, metric, ax, max_distance=35):
    ref_name = f'{technique}{46 if technique == "Mão" else 81 if technique == "Crânio" else 125}_1'
    reference = data[ref_name]['rows']
    colors = {1: '#1b4f72', 2: '#c03d35', 4: '#198754'}
    for mas in (1, 2, 4):
        name = f'{technique}{data[ref_name]["kvp"]}_{mas}'
        if name in INVALID:
            continue
        pairs = match(reference, data[name]['rows'], max_distance)
        valid = [(aid, row[metric]) for aid, (row, _) in pairs.items()
                 if not row['alertas'] and math.isfinite(row[metric])]
        valid.sort()
        if valid:
            ax.plot([p[0] for p in valid], [p[1] for p in valid], '.',
                    color=colors[mas], markersize=7,
                    label=f'{mas} mAs (n={len(valid)})')
    setup_ax(ax, f'{technique} | {data[ref_name]["kvp"]} kVp', PT[metric], len(reference))
    ax.legend(fontsize=8)


def plot_kvp(data, mas, ax):
    reference = data[f'Crânio81_{mas}']['rows']
    curves = []
    for technique, kvp, color in [('Mão', 46, '#1b4f72'),
                                  ('Crânio', 81, '#c03d35'),
                                  ('Tórax', 125, '#198754')]:
        name = f'{technique}{kvp}_{mas}'
        if name in INVALID:
            continue
        pairs = match(reference, data[name]['rows'])
        vals = [(aid, row['sinal_corrigido']) for aid, (row, _) in pairs.items()
                if not row['alertas'] and math.isfinite(row['sinal_corrigido'])]
        curves.append((kvp, color, dict(vals)))
    # Comparação de kVp exige as mesmas posições em todas as curvas disponíveis.
    common = set.intersection(*(set(v) for _, _, v in curves)) if curves else set()
    for kvp, color, vals in curves:
        scale = max((vals[i] for i in common), default=float('nan'))
        if not common or not math.isfinite(scale) or scale <= 0:
            continue
        x = sorted(common)
        ax.plot(x, [vals[i] / scale for i in x], '.', color=color,
                markersize=7, label=f'{kvp} kVp')
    setup_ax(ax, f'{mas} mAs | {len(common)} regiões comuns',
             'Sinal corrigido / máximo da curva', len(reference))
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8)
    return len(common)


def dicom_preview(path):
    pixels = pydicom.dcmread(path).pixel_array
    lo, hi = np.percentile(pixels, (1, 99))
    if hi <= lo:
        hi = lo + 1
    return np.clip((pixels.astype(np.float32) - lo) / (hi - lo), 0, 1)


def plot_dicom_panel(dicom_dir, technique, kvp, number, out):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
    for ax, mas in zip(axes, (1, 2, 4)):
        name = f'{technique}{kvp}_{mas}'
        ax.imshow(dicom_preview(dicom_dir / name), cmap='gray', vmin=0, vmax=1)
        ax.set_title(f'{name}' + (' | análise rejeitada' if name in INVALID else ''))
        ax.axis('off')
    fig.suptitle(f'Figura {number} (análoga) | {technique}: DICOMs 1, 2 e 4 mAs')
    save(fig, out)


def plot_roi_map(dicom_path, mask_path, out):
    with np.load(mask_path, allow_pickle=False) as archive:
        labels = archive['labels']
        y, x, h, w = map(int, archive['crop_bbox_yxwh'])
    pixels = pydicom.dcmread(dicom_path).pixel_array[y:y+h, x:x+w]
    lo, hi = np.percentile(pixels, (1, 99))
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(pixels, cmap='gray', vmin=lo, vmax=hi)
    ax.contour(labels > 0, levels=[.5], colors=['#f4d03f'], linewidths=.6)
    for id_ in np.unique(labels):
        if id_ == 0:
            continue
        yy, xx = np.where(labels == id_)
        ax.text(float(xx.mean()), float(yy.mean()), f'{id_:02d}',
                ha='center', va='center', fontsize=7, color='yellow',
                bbox={'facecolor': 'black', 'alpha': .5, 'pad': 1})
    ax.set_title('Figura 15 (análoga) | regiões segmentadas de Crânio81_1')
    ax.axis('off')
    save(fig, out)


def number(value, digits=2):
    return f'{value:.{digits}f}' if isinstance(value, (int, float)) and math.isfinite(value) else '—'


def build_report(data, figures, output, lote, revision, dicom_dir):
    esc = html.escape
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
             '<title>Resultados análogos ao TCC de William da Veiga</title>',
             '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:auto;padding:28px;color:#203040}'
             'h1,h2{color:#173f5f}figure{margin:30px 0;padding:15px;border:1px solid #dbe3ea;border-radius:8px}'
             'img{width:100%;height:auto}figcaption{font-size:14px;color:#46596a}'
             'table{border-collapse:collapse;width:100%;font-size:12px;margin-bottom:30px}'
             'th,td{padding:6px;border-bottom:1px solid #dbe3ea;text-align:right}th:first-child,td:first-child{text-align:left}'
             'th{background:#e9f1f5;position:sticky;top:0}tr.alerta{background:#fff0e7}'
             'tr.invalida{background:#fbe7e7}.scroll{overflow:auto}code{font-size:13px}</style></head><body>',
             '<h1>Resultados análogos às figuras do TCC</h1>',
             '<p>Fonte: lote processado por radio2. Estas figuras são novas análises das máscaras automáticas/revisadas; '
             'não reproduzem as ROIs manuais nem a identificação de profundidades do TCC.</p>',
             '<p>Fonte principal: <code>' + esc(str(lote)) + '</code><br>Revisão escolhida para Crânio81_1: '
             '<code>' + esc(str(revision) if revision else 'nenhuma') + '</code><br>DICOMs: <code>'
             + esc(str(dicom_dir)) + '</code></p>',
             '<h2>Método e limites</h2><p>Abscissa = ID espacial da região, ordenado por centroide na própria imagem '
             '(ou no DICOM de referência das comparações). Não é profundidade em mm. '
             'Correspondências entre imagens são provisórias: centroides absolutos a até 35 px, associação única '
             'pela menor distância. Comparações ignoram candidatos com alerta heurístico; gráficos individuais '
             'os mostram como círculos vazios. Lacunas não são preenchidas. Tórax125_2/4 estão excluídos '
             'das curvas quantitativas por detecção não confiável.</p>',
             '<p>Sinal bruto: média dos pixels DICOM originais no núcleo da máscara. '
             'Sinal corrigido: (bruto/fundo local) × mediana dos fundos locais válidos; é adaptação experimental, '
             'sem equivalência à ROI 12 do TCC. RSR = bruto/DP da ROI. RCR = |bruto - fundo local|/DP do fundo. '
             'O fundo é medido em anel em torno da máscara; o TCC usou regiões acima/abaixo. '
             'Nas comparações de kVp, cada curva é dividida pelo próprio máximo nas regiões comuns; '
             'a normalização exata do TCC não está documentada no texto.</p>',
             '<h2>Resumo das nove aquisições</h2><div class="scroll"><table><thead><tr>'
             '<th>DICOM</th><th>kVp</th><th>mAs</th><th>versão</th><th>regiões</th><th>alertas</th><th>uso quantitativo</th>'
             '</tr></thead><tbody>']
    for name, _, kvp, mas in EXPOSURES:
        item = data[name]; rows = item['rows']; invalid = name in INVALID
        parts.append(f'<tr class="{"invalida" if invalid else ""}"><td>{esc(name)}</td><td>{kvp}</td>'
                     f'<td>{mas}</td><td>{esc(item["version"])}</td><td>{len(rows)}</td>'
                     f'<td>{sum(bool(r["alertas"]) for r in rows)}</td>'
                     f'<td>{esc("excluído: " + INVALID[name] if invalid else "provisório")}</td></tr>')
    parts.append('</tbody></table></div><h2>Figuras</h2>')
    for num, filename, caption in figures:
        parts.append(f'<figure id="fig-{num}"><img src="figuras/{esc(filename)}" '
                     f'alt="Figura {num}"><figcaption>Figura {num} (análoga). {esc(caption)}</figcaption></figure>')
    parts.append('<h2>Tabelas de medições por DICOM</h2><p>R001, R002 etc. são IDs espaciais de cada execução; '
                 'não correspondem diretamente às profundidades nem às ROIs numeradas por William.</p>')
    columns = [('region_id', 'ID'), ('area_px', 'Área px'), ('sinal_bruto', 'S bruto'),
               ('desvio_padrao_roi', 'DP ROI'), ('fundo_local', 'Fundo'),
               ('desvio_padrao_fundo', 'DP fundo'), ('sinal_corrigido', 'S corrigido'),
               ('rsr', 'RSR'), ('rcr', 'RCR'), ('alertas', 'Alertas')]
    for name, _, _, _ in EXPOSURES:
        item = data[name]
        link = quote(os.path.relpath(item['source'] / 'resultados.csv', output))
        parts.append(f'<h3>{esc(name)} — {esc(item["version"])}</h3>'
                     f'<p><a href="{link}">Abrir tabela CSV de origem</a></p>'
                     '<div class="scroll"><table><thead><tr>'
                     + ''.join(f'<th>{esc(label)}</th>' for _, label in columns) + '</tr></thead><tbody>')
        for row in item['rows']:
            parts.append(f'<tr class="{"alerta" if row["alertas"] else ""}">')
            for key, _ in columns:
                value = row[key]
                if isinstance(value, float):
                    value = number(value, 0 if key == 'area_px' else 2)
                parts.append(f'<td>{esc(str(value))}</td>')
            parts.append('</tr>')
        parts.append('</tbody></table></div>')
    parts.append('<h2>Não reconstruído</h2><p>Figuras 1–14: revisão teórica, equipamento e fotografia do fantoma; '
                 'não derivam dos lotes. Valores por profundidade física, ROI 12 e fundo acima/abaixo exigem '
                 'anotação física/manual independente. Não há tabelas numeradas na lista de resultados do PDF.</p>'
                 '</body></html>')
    (output / 'index.html').write_text('\n'.join(parts), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lote', type=Path,
                        default=Path('resultados/lote_demonstracao_2026-11-16'))
    parser.add_argument('--revisao-cranio', type=Path,
                        default=Path('resultados/lote/001_Crânio81_1/revisoes/revisao_002'))
    parser.add_argument('--dicom-dir', type=Path, default=Path('dicom'))
    parser.add_argument('--saida', type=Path,
                        default=Path('resultados/recriacao_tcc_2026-11-16'))
    args = parser.parse_args()
    lote, revision, dicom_dir, output = (p.resolve() for p in
                                         (args.lote, args.revisao_cranio, args.dicom_dir, args.saida))
    summary = lote / 'resumo_lote.json'
    if not summary.is_file():
        parser.error(f'Lote sem resumo_lote.json: {lote}')
    index = {Path(row['arquivo']).name: row for row in json.loads(summary.read_text(encoding='utf-8'))}
    data = {}
    for name, technique, kvp, mas in EXPOSURES:
        if name not in index or index[name]['status'] != 'concluido':
            parser.error(f'Exposição ausente ou falhou no lote: {name}')
        source = Path(index[name]['diretorio']).resolve()
        version = 'automática'
        if name == 'Crânio81_1' and (revision / 'resultados.csv').is_file():
            source, version = revision, f'revisada ({revision.name})'
        data[name] = {'rows': load_rows(source / 'resultados.csv'), 'source': source,
                      'version': version, 'kvp': kvp, 'mas': mas, 'technique': technique}
    (output / 'figuras').mkdir(parents=True, exist_ok=True)
    figures = []
    def add(num, filename, caption, function):
        function(output / 'figuras' / filename)
        figures.append((num, filename, caption))
    add(15, 'fig15_regioes_cranio81_1.png', 'Máscaras medidas de Crânio81_1.',
        lambda out: plot_roi_map(dicom_dir / 'Crânio81_1',
                                 data['Crânio81_1']['source'] / 'mascaras.npz', out))
    for num, technique, kvp in [(16, 'Mão', 46), (17, 'Crânio', 81), (18, 'Tórax', 125)]:
        add(num, f'fig{num}_dicom_{technique.lower()}.png',
            f'DICOMs {technique}, escala por percentis 1–99 somente para visualização.',
            lambda out, t=technique, k=kvp, n=num: plot_dicom_panel(dicom_dir, t, k, n, out))
    singles = [(19, 'Mão46_1'), (20, 'Mão46_2'), (21, 'Mão46_4'),
               (22, 'Crânio81_1'), (23, 'Crânio81_2'), (24, 'Crânio81_4'),
               (25, 'Tórax125_1')]
    for num, name in singles:
        add(num, f'fig{num}_sinal_{name}.png',
            f'{name}: sinal bruto e correção experimental por ID espacial.',
            lambda out, n=name, i=num: plot_single(data, n, i, out))
    def fig26(out):
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
        for ax, technique in zip(axes, ('Mão', 'Crânio')):
            plot_comparison(data, technique, 'sinal_corrigido', ax)
        fig.suptitle('Figura 26 (análoga) | Sinal corrigido por carga')
        save(fig, out)
    add(26, 'fig26_carga_sinal.png', 'Comparação 1, 2 e 4 mAs em Mão e Crânio.', fig26)
    def fig27(out):
        fig, ax = plt.subplots(figsize=(8, 4.5)); plot_kvp(data, 1, ax)
        fig.suptitle('Figura 27 (análoga) | Comparação de kVp, 1 mAs')
        save(fig, out)
    add(27, 'fig27_kvp_1mas.png', 'Sinal corrigido normalizado por máximo, posições comuns.', fig27)
    def fig28(out):
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
        for ax, mas in zip(axes, (2, 4)):
            plot_kvp(data, mas, ax)
        fig.suptitle('Figura 28 (análoga) | Comparação de kVp, 2 e 4 mAs')
        save(fig, out)
    add(28, 'fig28_kvp_2_4mas.png', 'Tórax 2/4 mAs excluído por detecção não confiável.', fig28)
    for num, technique, metric in [(29, 'Mão', 'rsr'), (30, 'Crânio', 'rsr'),
                                   (31, 'Tórax', 'rsr'), (32, 'Mão', 'rcr'),
                                   (33, 'Crânio', 'rcr'), (34, 'Tórax', 'rcr')]:
        def plot(out, t=technique, m=metric, n=num):
            fig, ax = plt.subplots(figsize=(8, 4.5))
            plot_comparison(data, t, m, ax)
            fig.suptitle(f'Figura {n} (análoga) | {m.upper()} {t}')
            save(fig, out)
        add(num, f'fig{num}_{metric}_{technique.lower()}.png',
            f'{metric.upper()} de {technique}; Tórax 2/4 mAs omitidos.', plot)
    build_report(data, figures, output, lote, revision, dicom_dir)
    manifest = {'lote': str(lote), 'revisao_cranio': str(revision),
                'figuras': [{'numero': n, 'arquivo': f} for n, f, _ in figures],
                'fontes': {name: str(item['source']) for name, item in data.items()},
                'contagens': {name: len(item['rows']) for name, item in data.items()},
                'comparacao_espacial_max_distancia_px': 35,
                'imagens_excluidas_de_comparacoes': INVALID}
    (output / 'manifesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding='utf-8')
    print(f'{len(figures)} figuras e tabelas HTML de {len(data)} DICOMs: {output / "index.html"}')


if __name__ == '__main__':
    main()
