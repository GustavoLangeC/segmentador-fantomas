#!/usr/bin/env python3
"""Exporta metadados técnicos DICOM para o acompanhamento da IC.

Não exporta identificação do paciente, não lê pixel_array e não modifica os
DICOMs. O objetivo é documentar as condições de aquisição disponíveis para
comparar os resultados do segmentador entre técnicas e exposições.
"""
import argparse
import csv
import json
from pathlib import Path

import pydicom


FIELDS = (
    ('arquivo', None),
    ('linhas', 'Rows'),
    ('colunas', 'Columns'),
    ('fotometria', 'PhotometricInterpretation'),
    ('bits_armazenados', 'BitsStored'),
    ('bits_alocados', 'BitsAllocated'),
    ('representacao_pixel', 'PixelRepresentation'),
    ('modalidade', 'Modality'),
    ('fabricante', 'Manufacturer'),
    ('modelo_equipamento', 'ManufacturerModelName'),
    ('kvp', 'KVP'),
    ('exposicao_dicom', 'Exposure'),
    ('exposicao_uas', 'ExposureInuAs'),
    ('tempo_exposicao_ms', 'ExposureTime'),
    ('corrente_tubo_ma', 'XRayTubeCurrent'),
    ('distancia_fonte_detector_mm', 'DistanceSourceToDetector'),
    ('distancia_fonte_paciente_mm', 'DistanceSourceToPatient'),
    ('espacamento_pixel', 'PixelSpacing'),
)


def value_as_text(value):
    if value is None:
        return ''
    if isinstance(value, (str, int, float)):
        return str(value)
    try:
        return '\\'.join(str(item) for item in value)
    except TypeError:
        return str(value)


def collect(dicom_dir: Path):
    rows = []
    for path in sorted(item for item in dicom_dir.iterdir() if item.is_file()):
        dataset = pydicom.dcmread(path, stop_before_pixels=True)
        row = {}
        for name, keyword in FIELDS:
            row[name] = path.name if keyword is None else value_as_text(getattr(dataset, keyword, None))
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(
        description='Exporta somente metadados técnicos dos DICOMs para CSV e JSON.'
    )
    parser.add_argument('--dicom-dir', type=Path, default=Path('dicom'))
    parser.add_argument('--saida', type=Path, required=True,
                        help='Caminho do CSV; o JSON será criado ao lado.')
    args = parser.parse_args()
    if not args.dicom_dir.is_dir():
        raise FileNotFoundError(f'Diretório DICOM não encontrado: {args.dicom_dir}')
    rows = collect(args.dicom_dir)
    if not rows:
        raise RuntimeError(f'Nenhum arquivo encontrado em: {args.dicom_dir}')
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with args.saida.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=[name for name, _ in FIELDS])
        writer.writeheader()
        writer.writerows(rows)
    json_path = args.saida.with_suffix('.json')
    with json_path.open('w', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
    print(f'{len(rows)} DICOMs documentados em: {args.saida}')
    print(f'Metadados técnicos em JSON: {json_path}')


if __name__ == '__main__':
    main()
