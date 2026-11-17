"""Curvas exploratórias por profundidades fornecidas pelo usuário na interface.

Este módulo de análise não fornece geometria nem profundidade ao detector.
"""
import argparse
import csv
import html
import json
import math
import os
import re
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/radio2_matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .mapear_profundidades import latest_measurements, load_current_map


SINGLES = [(19, 'Mão46_1'), (20, 'Mão46_2'), (21, 'Mão46_4'),
           (22, 'Crânio81_1'), (23, 'Crânio81_2'), (24, 'Crânio81_4'),
           (25, 'Tórax125_1')]
METRICS = [('sinal_bruto', 'Sinal bruto (níveis DICOM)'),
           ('sinal_corrigido', 'Sinal corrigido experimental'),
           ('rsr', 'RSR'), ('rcr', 'RCR')]
COLORS = {1: '#1b4f72', 2: '#c03d35', 4: '#198754'}


def format_number(value):
    try:
        value = float(value)
        return f'{value:.2f}' if math.isfinite(value) else '—'
    except (ValueError, TypeError):
        return '—'


def read_dataset(lote):
    summary = json.loads((lote / 'resumo_lote.json').read_text(encoding='utf-8'))
    datasets, unavailable = {}, []
    for item in summary:
        name = Path(item['arquivo']).stem
        if not re.fullmatch(r'(Mão46|Crânio81|Tórax125)_[124]', name):
            unavailable.append((name, 'nome fora do conjunto experimental do TCC'))
            continue
        if item['status'] != 'concluido':
            unavailable.append((name, 'execução técnica falhou'))
            continue
        run_dir = latest_measurements(Path(item['diretorio']))
        try:
            mapping = load_current_map(run_dir)
        except ValueError as exc:
            unavailable.append((name, f'mapa desatualizado: {exc}'))
            continue
        if mapping is None:
            unavailable.append((name, 'profundidades ainda não informadas nessa versão das medições'))
            continue
        source = json.loads((run_dir / 'resultados.json').read_text(encoding='utf-8'))
        quality = source.get('qualidade_analise', {})
        with (run_dir / 'resultados.csv').open(newline='', encoding='utf-8') as stream:
            rows = {row['region_id']: row for row in csv.DictReader(stream)}
        if quality.get('estado') == 'inconclusiva' or (rows and all(r['alertas'] for r in rows.values())):
            unavailable.append((name, 'análise inconclusiva; curvas quantitativas omitidas'))
            continue
        mapped = []
        for entry in mapping['entries']:
            if entry['classe'] != 'inserto':
                continue
            row = rows.get(entry['region_id'])
            if row is None or entry['profundidade_mm'] is None:
                raise ValueError(f'{name}: mapa incompleto ou ID inexistente: {entry["region_id"]}')
            data = {'id': entry['region_id'], 'depth': float(entry['profundidade_mm']),
                    'alert': bool(row['alertas']), 'area_px': int(row['area_px'])}
            for metric, _ in METRICS:
                try:
                    data[metric] = float(row[metric])
                except (ValueError, TypeError):
                    data[metric] = float('nan')
            mapped.append(data)
        if len(mapped) < 2:
            unavailable.append((name, 'menos de dois insertos com profundidade informada'))
            continue
        datasets[name] = {'rows': sorted(mapped, key=lambda r: r['depth']),
                          'run_dir': run_dir,
                          'origem': mapping.get('origem'),
                          'map_hash': mapping['resultados_csv_sha256'],
                          'mapa': str(run_dir / 'mapa_profundidades.json'),
                          'mapeados': len(mapped),
                          'sem_alerta': sum(not r['alert'] for r in mapped)}
    return datasets, unavailable


def style(ax, title, ylabel):
    ax.set_title(title)
    ax.set_xlabel('Profundidade informada pelo usuário (mm)')
    ax.set_ylabel(ylabel)
    ax.grid(alpha=.25)


def finish(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches='tight')
    plt.close(fig)


def plot_single(name, dataset, number, path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, metric, part in zip(axes, ('sinal_bruto', 'sinal_corrigido'), ('A', 'B')):
        for flagged, label, color in ((False, 'sem alerta', '#126782'),
                                       (True, 'com alerta', '#d45227')):
            rows = [r for r in dataset['rows'] if r['alert'] == flagged and
                    math.isfinite(r[metric])]
            if rows:
                ax.scatter([r['depth'] for r in rows], [r[metric] for r in rows],
                           color=color, label=label, s=30)
        style(ax, f'{part}. {metric.replace("_", " ").title()}',
              'Níveis DICOM' if metric == 'sinal_bruto' else 'Correção experimental')
        ax.legend(fontsize=8)
    fig.suptitle(f'Figura {number} (análoga) | {name} | {dataset["mapeados"]} pontos mapeados')
    finish(fig, path)


def plot_series(ax, datasets, names, metric, title):
    plotted = 0
    for name, label, color in names:
        if name not in datasets:
            continue
        rows = [r for r in datasets[name]['rows'] if not r['alert'] and
                math.isfinite(r[metric])]
        if not rows:
            continue
        ax.scatter([r['depth'] for r in rows], [r[metric] for r in rows],
                   s=25, color=color, label=f'{label} (n={len(rows)})')
        plotted += 1
    style(ax, title, dict(METRICS)[metric])
    if plotted:
        ax.legend(fontsize=8)
    else:
        ax.text(.5, .5, 'Mapas/medidas insuficientes', ha='center', va='center',
                transform=ax.transAxes)
    return plotted


def plot_kvp(ax, datasets, mas):
    sources = [(f'Mão46_{mas}', '46 kVp', '#1b4f72'),
               (f'Crânio81_{mas}', '81 kVp', '#c03d35'),
               (f'Tórax125_{mas}', '125 kVp', '#198754')]
    curves = []
    for name, label, color in sources:
        if name not in datasets:
            continue
        grouped = {}
        for row in datasets[name]['rows']:
            if not row['alert'] and math.isfinite(row['sinal_corrigido']):
                grouped.setdefault(row['depth'], []).append(row['sinal_corrigido'])
        # Se houver profundidades repetidas, evita sobrescrever uma ROI pela outra.
        values = {depth: sum(samples) / len(samples)
                  for depth, samples in grouped.items()}
        if values:
            curves.append((label, color, values))
    if len(curves) < 2:
        style(ax, f'{mas} mAs', 'S corrigido / máximo da série')
        ax.text(.5, .5, 'Menos de duas técnicas mapeadas', ha='center', va='center',
                transform=ax.transAxes)
        return 0
    common = set.intersection(*(set(curve[2]) for curve in curves))
    if len(common) < 2:
        style(ax, f'{mas} mAs', 'S corrigido / máximo da série')
        ax.text(.5, .5, 'Menos de duas profundidades comuns', ha='center', va='center',
                transform=ax.transAxes)
        return 0
    x = sorted(common)
    for label, color, values in curves:
        scale = max(values[depth] for depth in x)
        if scale > 0:
            ax.scatter(x, [values[depth] / scale for depth in x], s=25,
                       label=label, color=color)
    style(ax, f'{mas} mAs | {len(x)} profundidades comuns',
          'S corrigido / máximo da série')
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8)
    return len(x)


def generate(lote, output):
    lote, output = Path(lote).resolve(), Path(output).resolve()
    data, missing = read_dataset(lote)
    (output / 'figuras').mkdir(parents=True, exist_ok=True)
    figures = []
    for number, name in SINGLES:
        if name in data:
            filename = f'fig{number}_{name}.png'
            plot_single(name, data[name], number, output / 'figuras' / filename)
            figures.append((number, filename, name))
    if any(f'Mão46_{m}' in data or f'Crânio81_{m}' in data for m in (1, 2, 4)):
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
        for ax, technique in zip(axes, ('Mão46', 'Crânio81')):
            plot_series(ax, data, [(f'{technique}_{mas}', f'{mas} mAs', COLORS[mas])
                                   for mas in (1, 2, 4)],
                        'sinal_corrigido', technique)
        fig.suptitle('Figura 26 (análoga) | comparação das cargas')
        filename = 'fig26_cargas.png'; finish(fig, output / 'figuras' / filename)
        figures.append((26, filename, 'Comparação de 1, 2 e 4 mAs'))
    for number, masses in ((27, (1,)), (28, (2, 4))):
        fig, axes = plt.subplots(1, len(masses), figsize=(7 * len(masses), 4.5))
        axes = [axes] if len(masses) == 1 else axes
        counts = [plot_kvp(ax, data, mas) for ax, mas in zip(axes, masses)]
        if any(counts):
            fig.suptitle(f'Figura {number} (análoga) | comparação normalizada de kVp')
            filename = f'fig{number}_kvp.png'; finish(fig, output / 'figuras' / filename)
            figures.append((number, filename, f'kVp em {masses} mAs'))
        else:
            plt.close(fig)
    for number, technique, metric in ((29, 'Mão46', 'rsr'), (30, 'Crânio81', 'rsr'),
                                      (31, 'Tórax125', 'rsr'), (32, 'Mão46', 'rcr'),
                                      (33, 'Crânio81', 'rcr'), (34, 'Tórax125', 'rcr')):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        plotted = plot_series(ax, data,
                              [(f'{technique}_{mas}', f'{mas} mAs', COLORS[mas])
                               for mas in (1, 2, 4)], metric, technique)
        if plotted:
            fig.suptitle(f'Figura {number} (análoga) | {metric.upper()} {technique}')
            filename = f'fig{number}_{metric}_{technique}.png'
            finish(fig, output / 'figuras' / filename)
            figures.append((number, filename, f'{metric.upper()} {technique}'))
        else:
            plt.close(fig)
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
             '<title>Curvas por profundidade informada</title>',
             '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:auto;padding:28px}'
             'img{max-width:100%}figure{padding:12px;border:1px solid #ddd;margin:24px 0}'
             'table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:5px}'
             '</style></head><body><h1>Curvas por profundidade informada</h1>',
             '<p>As profundidades foram informadas pelo usuário ou transferidas por posição após a detecção; '
             'as transferidas aguardam conferência visual. Não são inferidas da ordem do sinal '
             'e não entram no detector. Máscaras e profundidades ainda exigem verificação independente. '
             'Sinal corrigido e fundo local diferem da metodologia literal da ROI 12 do TCC.</p>',
             f'<p>Lote: <code>{html.escape(str(lote))}</code>. Imagens com mapa utilizável: {len(data)}. '
             f'Figuras geradas: {len(figures)}.</p>',
             '<h2>Imagens sem curva quantitativa</h2><ul>']
    for name, reason in missing:
        parts.append(f'<li>{html.escape(name)}: {html.escape(reason)}</li>')
    if not missing:
        parts.append('<li>Nenhuma.</li>')
    parts.append('</ul><h2>Figuras</h2>')
    for number, filename, caption in figures:
        parts.append(f'<figure><img src="figuras/{html.escape(filename)}" '
                     f'alt="Figura {number}"><figcaption>Figura {number} (análoga): '
                     f'{html.escape(caption)}.</figcaption></figure>')
    parts.append('<h2>Regiões com profundidade informada</h2><table><thead><tr><th>DICOM</th>'
                 '<th>Origem do mapa</th><th>ID</th><th>Profundidade (mm)</th><th>Área (px)</th><th>S bruto</th>'
                 '<th>S corrigido</th><th>RSR</th><th>RCR</th><th>Alerta</th></tr></thead><tbody>')
    for name, item in sorted(data.items()):
        for row in item['rows']:
            parts.append('<tr>' + ''.join(f'<td>{html.escape(value)}</td>' for value in
                         (name, 'transferida; conferir' if
                          (item['origem'] or '').startswith('transferencia_') else
                          'informada pelo usuário', row['id'],
                          f"{row['depth']:g}", str(row['area_px']),
                          format_number(row['sinal_bruto']), format_number(row['sinal_corrigido']),
                          format_number(row['rsr']), format_number(row['rcr']),
                          'sim' if row['alert'] else 'não')) + '</tr>')
    parts.append('</tbody></table></body></html>')
    (output / 'index.html').write_text('\n'.join(parts), encoding='utf-8')
    manifest = {'lote': str(lote), 'origem_profundidades': 'informada_pelo_usuario_na_interface',
                'imagens': {name: {'mapa': item['mapa'],
                                  'origem': item['origem'],
                                  'csv_sha256': item['map_hash'],
                                  'pontos_mapeados': item['mapeados'],
                                  'pontos_sem_alerta': item['sem_alerta']}
                            for name, item in data.items()},
                'omitidas': [{'imagem': name, 'motivo': reason} for name, reason in missing],
                'figuras': [{'numero': n, 'arquivo': file} for n, file, _ in figures]}
    (output / 'manifesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding='utf-8')
    return output / 'index.html', manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lote', type=Path, required=True)
    parser.add_argument('--saida', type=Path)
    args = parser.parse_args()
    output = args.saida or args.lote / 'curvas_fisicas'
    page, manifest = generate(args.lote, output)
    print(f'{len(manifest["figuras"])} figuras por profundidade informada: {page}')


if __name__ == '__main__':
    main()
