#!/usr/bin/env python3
"""Organiza rascunhos automáticos e destaca regiões que pedem revisão.

As máscaras aqui vêm do mesmo detector em duas sensibilidades. Concordância
entre elas mede estabilidade de parâmetros, não acurácia nem verdade manual.
"""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pydicom
from scipy.optimize import linear_sum_assignment


def read_run(directory):
    with (directory / 'resultados.json').open(encoding='utf-8') as stream:
        info = json.load(stream)
    with np.load(directory / 'mascaras.npz', allow_pickle=False) as archive:
        labels = archive['labels']
        bbox = archive['crop_bbox_yxwh']
    return info, labels, bbox


def associate(first, second):
    """Calcula IoU por tabela de contingência, sem matrizes 2D por objeto."""
    n, m = int(first.max()), int(second.max())
    table = np.bincount((first.astype(np.int64) * (m + 1) + second).ravel(),
                        minlength=(n + 1) * (m + 1)).reshape(n + 1, m + 1)
    count_a = table.sum(axis=1)
    count_b = table.sum(axis=0)
    overlap = table[1:, 1:]
    union = count_a[1:, None] + count_b[None, 1:] - overlap
    iou = np.divide(overlap, union, out=np.zeros_like(overlap, dtype=float),
                    where=union > 0)
    pairs = {}
    if iou.size:
        rows, cols = linear_sum_assignment(-iou)
        for row, col in zip(rows, cols):
            if iou[row, col] > 0:
                pairs[row + 1] = (col + 1, float(iou[row, col]))
    return pairs, set(range(1, m + 1)) - {pair[0] for pair in pairs.values()}


def canvas_for_review(pixels, labels, rows, bbox, labels_alt, new_ids):
    y, x, height, width = map(int, bbox)
    crop = pixels[y:y + height, x:x + width]
    lo, hi = np.percentile(crop, (1, 99))
    gray = np.uint8(np.clip((crop.astype(np.float32) - lo) *
                            (255 / max(hi - lo, 1)), 0, 255))
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    colors = {'estavel': (40, 190, 40), 'revisar': (0, 175, 255),
              'suspeita': (20, 20, 230)}
    for row in rows:
        idx = int(row['id'])
        mask = np.uint8(labels == idx)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        color = colors[row['estado']]
        cv2.drawContours(canvas, contours, -1, color, 2)
        px, py = int(round(float(row['centro_x']))), int(round(float(row['centro_y'])))
        cv2.putText(canvas, f'{idx}', (px + 4, py - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, f'{idx}', (px + 4, py - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    for idx in sorted(new_ids):
        mask = np.uint8(labels_alt == idx)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, (225, 0, 225), 2)
        ys, xs = np.nonzero(mask)
        if xs.size:
            cv2.putText(canvas, f'A{idx}', (int(xs.mean()) + 4, int(ys.mean()) - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (225, 0, 225), 2, cv2.LINE_AA)
    return canvas


def prepare(dicom_path, baseline, alternate, output):
    base, labels, bbox = read_run(baseline)
    alt, labels_alt, bbox_alt = read_run(alternate)
    if labels.shape != labels_alt.shape or not np.array_equal(bbox, bbox_alt):
        raise ValueError(f'{dicom_path.name}: recortes diferentes; registro necessário antes da comparação.')
    pairs, new_ids = associate(labels, labels_alt)
    rows = []
    for idx, obj in enumerate(base['objects'], start=1):
        match, iou = pairs.get(idx, (None, 0.0))
        alerts = obj.get('alertas', '')
        large = int(obj['area_px']) > 0.05 * labels.size
        concern = bool(alerts) or large
        state = 'suspeita' if concern else ('estavel' if iou >= 0.7 else 'revisar')
        rows.append({
            'id': idx, 'estado': state, 'area_px': obj['area_px'],
            'centro_x': obj['centro_x_recorte_px'],
            'centro_y': obj['centro_y_recorte_px'],
            'par_sensibilidade_1_2': match if match is not None else '',
            'iou_entre_execucoes': round(iou, 4), 'alertas_detector': alerts,
        })
    dataset = pydicom.dcmread(dicom_path)
    pixels = dataset.pixel_array
    if pixels.ndim != 2:
        raise ValueError('A visualização requer um DICOM 2D.')
    if pixels.shape[0] < bbox[0] + bbox[2] or pixels.shape[1] < bbox[1] + bbox[3]:
        raise ValueError('Recorte fora dos limites do DICOM.')
    output.mkdir(parents=True, exist_ok=True)
    canvas = canvas_for_review(pixels, labels, rows, bbox, labels_alt, new_ids)
    if not cv2.imwrite(str(output / 'revisao.png'), canvas):
        raise OSError('Falha ao salvar a visualização.')
    if labels.max() > np.iinfo(np.uint16).max:
        raise ValueError('Rótulos excedem o limite do TIFF de 16 bits.')
    y, x, height, width = map(int, bbox)
    if not cv2.imwrite(str(output / 'imagem_recortada_bruta.tif'),
                       pixels[y:y + height, x:x + width]):
        raise OSError('Falha ao salvar o recorte bruto TIFF.')
    if not cv2.imwrite(str(output / 'rascunho_rotulos.tif'),
                       labels.astype(np.uint16)):
        raise OSError('Falha ao salvar os rótulos TIFF.')
    with (output / 'fila.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else
                                ['id', 'estado', 'area_px', 'centro_x', 'centro_y',
                                 'par_sensibilidade_1_2', 'iou_entre_execucoes',
                                 'alertas_detector'])
        writer.writeheader()
        writer.writerows(rows)
    # Nome proposital: essas máscaras são cópia automática e NÃO referência manual.
    np.savez_compressed(output / 'rascunho_automatico.npz',
                        labels=labels.astype(np.int32), crop_bbox_yxwh=bbox)
    summary = {'dicom': dicom_path.name, 'origem': 'detector; sensibilidades 1.5 e 1.2',
               'status': 'rascunho_automatico_nao_validado',
               'regioes_base': len(rows), 'regioes_alternativas': int(labels_alt.max()),
               'novas_regioes_1_2': sorted(new_ids),
               'estaveis_sem_alerta': sum(r['estado'] == 'estavel' for r in rows),
               'a_revisar': sum(r['estado'] != 'estavel' for r in rows)}
    (output / 'resumo.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                        encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dicom', type=Path)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('alternativa', type=Path)
    parser.add_argument('saida', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.dicom, args.baseline, args.alternativa, args.saida),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
