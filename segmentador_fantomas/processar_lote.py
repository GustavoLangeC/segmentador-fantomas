"""Processa vários DICOMs sequencialmente e registra erros por arquivo."""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import pydicom


def dicom_files(paths, directory):
    files = [Path(p).resolve() for p in paths]
    if directory:
        files.extend(sorted(p.resolve() for p in directory.iterdir() if p.is_file()))
    if not files:
        raise ValueError('Informe arquivos DICOM ou --dicom-dir.')
    unique = list(dict.fromkeys(files))
    for path in unique:
        if not path.is_file():
            raise FileNotFoundError(path)
    return unique


def process(files, output, sensitivity=1.5, min_area=0):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Diretório de saída já contém dados: {output}')
    output.mkdir(parents=True, exist_ok=True)
    main = Path(__file__).resolve().parent.parent / 'main.py'
    rows = []
    for index, path in enumerate(files, 1):
        started = time.perf_counter()
        name = f'{index:03d}_{path.stem}'
        destination = output / name
        try:
            pydicom.dcmread(path, stop_before_pixels=True, force=False)
            cmd = [sys.executable, str(main), str(path), '--sem-janela',
                   '--sensibilidade', str(sensitivity), '--min-area', str(min_area),
                   '--output-dir', str(destination)]
            destination.mkdir(parents=True, exist_ok=True)
            run = subprocess.run(cmd, cwd=destination, capture_output=True, text=True)
            (destination / 'execucao.log').write_text(run.stdout + '\n' + run.stderr,
                                                     encoding='utf-8')
            if run.returncode:
                raise RuntimeError(f'Código {run.returncode}; veja execucao.log')
            metadata = json.loads((destination / 'resultados.json').read_text(encoding='utf-8'))
            status, count, detail = 'concluido', metadata['detected_regions'], ''
            alerts = sum(bool(obj.get('alertas')) for obj in metadata['objects'])
            quality = metadata.get('qualidade_analise', {})
            analysis_state = quality.get('estado', 'não avaliada')
            analysis_reasons = ';'.join(quality.get('motivos', []))
        except Exception as exc:
            status, count, detail = 'falha', '', str(exc)
            alerts = ''
            analysis_state, analysis_reasons = 'não avaliada', ''
        row = {'arquivo': str(path), 'diretorio': str(destination), 'status': status,
               'regioes': count, 'regioes_com_alerta': alerts,
               'qualidade_analise': analysis_state,
               'motivos_qualidade': analysis_reasons,
               'detalhe': detail, 'sensibilidade': sensitivity,
               'min_area': min_area, 'duracao_s': round(time.perf_counter()-started, 3)}
        rows.append(row)
        print(f'{index}/{len(files)} {path.name}: {status} '
              f'({count} regiões, {alerts} com alerta; análise {analysis_state}) '
              f'{detail}', flush=True)
    with (output / 'resumo_lote.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output / 'resumo_lote.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                            encoding='utf-8')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arquivos', type=Path, nargs='*')
    parser.add_argument('--dicom-dir', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--sensibilidade', type=float, default=1.5)
    parser.add_argument('--min-area', type=int, default=0)
    args = parser.parse_args()
    if args.sensibilidade <= 0 or args.min_area < 0:
        parser.error('Sensibilidade deve ser positiva e área mínima não negativa.')
    rows = process(dicom_files(args.arquivos, args.dicom_dir), args.output_dir.resolve(),
                   args.sensibilidade, args.min_area)
    return 1 if any(row['status'] == 'falha' for row in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
