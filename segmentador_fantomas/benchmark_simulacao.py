"""Executa os cenários simulados e reúne TP/FP/FN/IoU num índice auditável."""
import argparse
import csv
import html
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from .interface import SIMULATION_MODES, run_simulation_workflow


def run_all(sim_root, output, include_xrmc=True):
    sim_root, output = Path(sim_root).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Diretório de saída já contém dados: {output}')
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for mode, preset in SIMULATION_MODES.items():
        if preset is None and not include_xrmc:
            continue
        slug = preset or 'xrmc_minimo'
        case = output / slug
        try:
            result = run_simulation_workflow(sim_root, mode, case, sys.executable)
        except Exception as exc:
            result = SimpleNamespace(returncode=1, stdout='', stderr=str(exc))
        row = {'cenario': mode, 'diretorio': str(case),
               'status': 'concluido' if result.returncode == 0 else 'falha',
               'tp': '', 'fp': '', 'fn': '', 'iou_pixel': '',
               'qualidade': '', 'erro': ''}
        (case / 'execucao.log').parent.mkdir(parents=True, exist_ok=True)
        (case / 'execucao.log').write_text(result.stdout + '\n' + result.stderr,
                                          encoding='utf-8')
        if result.returncode == 0:
            folder = case / 'avaliacao'
            metrics = json.loads((folder / 'avaliacao_referencia.json').read_text(encoding='utf-8'))
            assessment = json.loads((folder / 'resultados.json').read_text(encoding='utf-8'))
            row.update({'tp': metrics['true_positives'], 'fp': metrics['false_positives'],
                        'fn': metrics['false_negatives'],
                        'iou_pixel': round(metrics['pixel_iou_foreground'], 6),
                        'qualidade': assessment['qualidade_analise']['estado']})
        else:
            row['erro'] = (result.stderr or result.stdout).strip()[-500:]
        rows.append(row)
        print(f"{mode}: {row['status']} TP={row['tp']} FP={row['fp']} "
              f"FN={row['fn']} IoU={row['iou_pixel']}", flush=True)
    with (output / 'resumo.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / 'resumo.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                       encoding='utf-8')
    body = []
    for row in rows:
        slug = Path(row['diretorio']).name
        link = (f'<a href="{html.escape(slug)}/avaliacao/relatorio_simulacao.html">Abrir</a>'
                if row['status'] == 'concluido' else '—')
        body.append('<tr>' + ''.join(f'<td>{html.escape(str(row[key]))}</td>' for key in
                                    ('cenario', 'status', 'tp', 'fp', 'fn', 'iou_pixel', 'qualidade'))
                    + f'<td>{link}</td></tr>')
    page = ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<title>Benchmark de simulações</title><h1>Benchmark de simulações</h1>'
            '<p>Casos ilustrativos. TP/FP/FN exigem a referência do cenário e não medem '
            'acurácia nos DICOMs reais.</p><table border="1" cellpadding="6"><tr>'
            '<th>Cenário</th><th>Status</th><th>TP</th><th>FP</th><th>FN</th>'
            '<th>IoU por pixel</th><th>Qualidade heurística</th><th>Relatório</th></tr>'
            + ''.join(body) + '</table></html>')
    (output / 'index.html').write_text(page, encoding='utf-8')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulacao', type=Path, default=Path('../simulacao-xrmc'))
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--sem-xrmc', action='store_true', help='Executa só cenários analíticos.')
    args = parser.parse_args()
    rows = run_all(args.simulacao, args.saida, not args.sem_xrmc)
    print(f'Índice: {args.saida / "index.html"}')
    return 1 if any(row['status'] == 'falha' for row in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
