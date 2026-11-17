"""Associação física informada pelo usuário, separada da detecção de insertos."""
import argparse
import csv
import hashlib
import html
import json
import math
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser


CLASSES = ('não avaliado', 'inserto', 'artefato', 'incerto')


def normalize_assignment(classification, value, id_):
    """Valida uma associação física sem depender da detecção ou da UI."""
    if classification not in CLASSES:
        raise ValueError(f'Classe inválida para {id_}: {classification}')
    typed = str(value if value is not None else '').strip()
    if classification == 'inserto':
        if not typed:
            raise ValueError(f'Informe a profundidade de {id_} ou marque como incerto.')
        try:
            depth = float(typed.replace(',', '.'))
        except ValueError as exc:
            raise ValueError(f'Profundidade inválida para {id_}: {typed}') from exc
        if not math.isfinite(depth) or depth < 0:
            raise ValueError(f'Profundidade de {id_} deve ser finita e não negativa.')
        return depth
    if typed:
        raise ValueError(f'Apague a profundidade de {id_} ou marque como inserto.')
    return None


def read_rows(run_dir):
    path = Path(run_dir) / 'resultados.csv'
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    required = {'region_id', 'centro_x_imagem_px', 'centro_y_imagem_px',
                'area_px', 'sinal_bruto', 'sinal_corrigido', 'rsr', 'rcr', 'alertas'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f'Tabela de medições vazia ou incompleta: {path}')
    ids = [row['region_id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('IDs espaciais duplicados na tabela de medições.')
    return rows


def csv_hash(run_dir):
    return hashlib.sha256((Path(run_dir) / 'resultados.csv').read_bytes()).hexdigest()


def load_current_map(run_dir):
    path = Path(run_dir) / 'mapa_profundidades.json'
    if not path.is_file():
        return None
    result = json.loads(path.read_text(encoding='utf-8'))
    if result.get('resultados_csv_sha256') != csv_hash(run_dir):
        raise ValueError('O mapa existente pertence a outra versão de resultados.csv; confira os IDs antes de reutilizar.')
    return result


def latest_measurements(run_dir):
    """Escolhe a versão mais recente do CSV, inclusive uma revisão de máscara."""
    run_dir = Path(run_dir)
    revisions = sorted((p for p in (run_dir / 'revisoes').glob('revisao_*')
                        if p.is_dir() and (p / 'resultados.csv').is_file()), reverse=True)
    return revisions[0] if revisions else run_dir


def save_mapping(run_dir, assignments, notes='', *,
                 origin='associacao_fisica_informada_pelo_usuario', provenance=None):
    """Valida entradas livres e versiona o mapa; não modifica máscaras ou CSV."""
    run_dir = Path(run_dir)
    rows = read_rows(run_dir)
    ids = {row['region_id'] for row in rows}
    if set(assignments) != ids:
        raise ValueError('O mapa precisa conter exatamente os IDs desta execução.')
    entries = []
    for row in rows:
        id_ = row['region_id']
        item = assignments[id_]
        classification = item['classe']
        depth = normalize_assignment(classification, item.get('profundidade_mm', ''), id_)
        entries.append({'region_id': id_, 'classe': classification,
                        'profundidade_mm': depth,
                        'centro_x_imagem_px': float(row['centro_x_imagem_px']),
                        'centro_y_imagem_px': float(row['centro_y_imagem_px'])})
    original = json.loads((run_dir / 'resultados.json').read_text(encoding='utf-8'))
    mapping = {'schema_version': 1, 'origem': origin,
               'validacao_independente': False,
               'dicom': original.get('dicom'),
               'resultados_csv_sha256': csv_hash(run_dir),
               'criado_em': datetime.now().isoformat(timespec='seconds'),
               'observacoes': notes.strip(), 'entries': entries,
               'contagem': {kind: sum(e['classe'] == kind for e in entries)
                            for kind in CLASSES}}
    if provenance is not None:
        mapping['proveniencia_transferencia'] = provenance
    version = 1
    while (run_dir / f'mapa_profundidades_{version:03d}.json').exists():
        version += 1
    versioned = run_dir / f'mapa_profundidades_{version:03d}.json'
    content = json.dumps(mapping, ensure_ascii=False, indent=2)
    versioned.write_text(content, encoding='utf-8')
    (run_dir / 'mapa_profundidades.json').write_text(content, encoding='utf-8')
    return versioned, mapping


def generate_single_curves(run_dir):
    """Cria gráfico exploratório por profundidade apenas dos insertos mapeados."""
    run_dir = Path(run_dir)
    mapping = load_current_map(run_dir)
    if mapping is None:
        raise ValueError('Mapa de profundidades ausente.')
    rows = {row['region_id']: row for row in read_rows(run_dir)}
    plotted = []
    for entry in mapping['entries']:
        if entry['classe'] == 'inserto':
            row = rows[entry['region_id']]
            plotted.append((entry['profundidade_mm'], row))
    if not plotted:
        return None
    import os
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/radio2_matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fields = [('sinal_bruto', 'Sinal bruto'),
              ('sinal_corrigido', 'Sinal corrigido experimental'),
              ('rsr', 'RSR'), ('rcr', 'RCR')]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, (field, title) in zip(axes.flat, fields):
        for flagged, color, label in [(False, '#126782', 'sem alerta'),
                                      (True, '#d45227', 'com alerta')]:
            values = []
            for depth, row in plotted:
                if bool(row['alertas']) != flagged:
                    continue
                try:
                    value = float(row[field])
                except (ValueError, TypeError):
                    continue
                if math.isfinite(value):
                    values.append((depth, value))
            if values:
                ax.scatter([p[0] for p in values], [p[1] for p in values],
                           color=color, label=label, s=25)
        ax.set_title(title); ax.set_xlabel('Profundidade informada (mm)')
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.suptitle(f"Curvas por profundidade informada | {Path(mapping['dicom']).name}")
    fig.tight_layout()
    png = run_dir / 'curvas_profundidade.png'
    fig.savefig(png, dpi=160)
    plt.close(fig)
    quality = json.loads((run_dir / 'resultados.json').read_text(encoding='utf-8')).get('qualidade_analise', {})
    inconclusive = quality.get('estado') == 'inconclusiva' or (
        bool(rows) and all(row['alertas'] for row in rows.values()))
    warning = ('Análise inconclusiva: valores exibidos apenas para inspeção.'
               if inconclusive else
               'Associação transferida por posição, pendente de conferência visual.'
               if mapping.get('origem', '').startswith('transferencia_') else
               'A associação física foi informada pelo usuário e não foi validada de modo independente.')
    body = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
            '<title>Curvas por profundidade informada</title>',
            '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:auto;padding:24px}'
            'img{max-width:100%}table{border-collapse:collapse;width:100%}'
            'td,th{border-bottom:1px solid #ccd7dc;padding:5px;text-align:right}'
            'td:first-child,th:first-child{text-align:left}</style></head><body>',
            f'<h1>Curvas por profundidade informada — {html.escape(Path(mapping["dicom"]).name)}</h1>',
            f'<p><strong>{html.escape(warning)}</strong> A profundidade não participa da detecção. '
            f'{len(plotted)} de {len(rows)} regiões foram classificadas como insertos com profundidade.</p>',
            '<p>O sinal bruto vem dos pixels DICOM originais. O sinal corrigido é uma adaptação experimental; '
            'o fundo é estimado em anel, diferente do protocolo da ROI 12 do TCC.</p>',
            '<img src="curvas_profundidade.png" alt="Quatro gráficos por profundidade informada">',
            '<h2>Associação informada</h2><table><thead><tr><th>ID espacial</th><th>Classe</th>'
            '<th>Profundidade (mm)</th><th>Sinal bruto</th><th>Sinal corrigido</th><th>RSR</th><th>RCR</th>'
            '</tr></thead><tbody>']
    for entry in mapping['entries']:
        row = rows[entry['region_id']]
        values = [entry['region_id'], entry['classe'],
                  '—' if entry['profundidade_mm'] is None else f"{entry['profundidade_mm']:g}"]
        for field in ('sinal_bruto', 'sinal_corrigido', 'rsr', 'rcr'):
            try:
                value = float(row[field]); values.append(f'{value:.2f}' if math.isfinite(value) else '—')
            except (ValueError, TypeError):
                values.append('—')
        body.append('<tr>' + ''.join(f'<td>{html.escape(v)}</td>' for v in values) + '</tr>')
    body.append('</tbody></table></body></html>')
    page = run_dir / 'curvas_profundidade.html'
    page.write_text('\n'.join(body), encoding='utf-8')
    return page


class MappingWindow:
    def __init__(self, root, run_dir):
        self.root, self.run_dir = root, Path(run_dir)
        self.rows = read_rows(self.run_dir)
        try:
            current = load_current_map(self.run_dir)
        except ValueError as exc:
            current = None
            messagebox.showwarning('Mapa anterior incompatível', str(exc))
        previous = {e['region_id']: e for e in current['entries']} if current else {}
        root.title(f'Associar profundidades — {self.run_dir.name}')
        root.geometry('850x730')
        tk.Label(root, text='Identificação física posterior à detecção: confira cada ID na imagem. '
                            'Deixe incerto quando não souber a profundidade.', wraplength=800).pack(pady=8)
        image_path = next(iter(self.run_dir.glob('resultado_*.png')), None)
        if image_path is None:
            image_path = self.run_dir / 'resultado_revisado.png'
        if image_path.is_file():
            tk.Button(root, text='Abrir imagem com IDs',
                      command=lambda: webbrowser.open(image_path.resolve().as_uri())).pack()
        frame = tk.Frame(root); frame.pack(fill='both', expand=True)
        canvas = tk.Canvas(frame)
        scroll = tk.Scrollbar(frame, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        for col, title in enumerate(('ID', 'Centro na imagem (px)', 'Área (px)', 'Classe', 'Profundidade (mm)')):
            tk.Label(inner, text=title, font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=col, padx=8, pady=4)
        self.controls = {}
        for idx, row in enumerate(self.rows, 1):
            id_ = row['region_id']
            old = previous.get(id_, {})
            classification = tk.StringVar(value=old.get('classe', CLASSES[0]))
            depth = tk.StringVar(value='' if old.get('profundidade_mm') is None else
                                 str(old['profundidade_mm']))
            tk.Label(inner, text=id_).grid(row=idx, column=0, padx=8, pady=3)
            center = f"({float(row['centro_x_imagem_px']):.0f}, {float(row['centro_y_imagem_px']):.0f})"
            tk.Label(inner, text=center).grid(row=idx, column=1, padx=8)
            tk.Label(inner, text=row['area_px']).grid(row=idx, column=2, padx=8)
            ttk.Combobox(inner, textvariable=classification, values=CLASSES,
                         state='readonly', width=16).grid(row=idx, column=3, padx=8)
            tk.Entry(inner, textvariable=depth, width=14).grid(row=idx, column=4, padx=8)
            self.controls[id_] = (classification, depth)
        tk.Label(root, text='Observações sobre furos ausentes, ambiguidades ou orientação:').pack(anchor='w')
        self.notes = tk.Text(root, height=3)
        self.notes.pack(fill='x', padx=8)
        if current:
            self.notes.insert('1.0', current.get('observacoes', ''))
        tk.Button(root, text='Salvar mapa e gerar curvas', command=self.save).pack(pady=8)

    def save(self):
        assignments = {id_: {'classe': classification.get(), 'profundidade_mm': depth.get()}
                       for id_, (classification, depth) in self.controls.items()}
        try:
            path, mapping = save_mapping(self.run_dir, assignments,
                                         self.notes.get('1.0', 'end').strip())
            curves = generate_single_curves(self.run_dir)
        except Exception as exc:
            messagebox.showerror('Falha no mapa', str(exc)); return
        messagebox.showinfo('Mapa salvo', f'Mapa: {path}\n'
                            f'Insertos com profundidade: {mapping["contagem"]["inserto"]}\n'
                            f'Curvas: {curves or "ainda sem insertos mapeados"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resultado', type=Path, help='Pasta com resultados.csv/json e máscaras.')
    args = parser.parse_args()
    root = tk.Tk()
    MappingWindow(root, args.resultado.resolve())
    root.mainloop()


if __name__ == '__main__':
    main()
