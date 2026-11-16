"""Exportacao e avaliacao de segmentacoes, sem conhecimento do fantoma.

As funcoes deste modulo sao deliberadamente separadas do detector: rotulos de
referencia sao usados apenas para medir resultados, nunca para orientar a
segmentacao automatica.
"""
import csv
import json
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment


def _json_value(value):
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    return value


def object_quality(objects, labels, global_noise, min_area, max_area):
    """Adiciona alertas heurísticos, não uma probabilidade calibrada.

    Os critérios usam apenas máscara, contraste e vizinhança entre candidatos;
    não usam contagem, forma esperada, posições, grade ou dados do fantoma.
    """
    for obj in objects:
        flags = []
        bg = obj.get('background', float('nan'))
        bg_std = obj.get('background_std', float('nan'))
        contrast = abs(obj['mean'] - bg) if np.isfinite(bg) else float('nan')
        denominator = np.hypot(obj.get('std', 0.0), bg_std) if np.isfinite(bg_std) else float('nan')
        local_cnr = contrast / denominator if denominator > 0 else float('nan')
        obj['local_cnr'] = float(local_cnr)
        obj['rsr'] = float(obj['mean'] / obj['std']) if obj['std'] > 0 else float('nan')
        obj['rcr'] = float(contrast / bg_std) if np.isfinite(bg_std) and bg_std > 0 else float('nan')
        if not np.isfinite(bg):
            flags.append('fundo_local_indisponivel')
        if np.isfinite(local_cnr) and local_cnr < 1.5:
            flags.append('contraste_local_baixo')
        if obj['area_px'] <= 1.15 * min_area:
            flags.append('proximo_da_area_minima')
        if obj['area_px'] >= 0.85 * max_area:
            flags.append('proximo_da_area_maxima')
        obj['quality_flags'] = flags

    # Proximidade de caixas, normalizada pela escala das próprias máscaras. Isso
    # só gera alerta: não mescla nem descarta candidatos automaticamente.
    for a, b in combinations(objects, 2):
        ay0, ay1, ax0, ax1 = _bbox(a)
        by0, by1, bx0, bx1 = _bbox(b)
        dy = max(0, max(ay0, by0) - min(ay1, by1))
        dx = max(0, max(ax0, bx0) - min(ax1, bx1))
        gap = float(np.hypot(dy, dx))
        scale = max(3.0, 0.12 * min(np.sqrt(a['area_px']), np.sqrt(b['area_px'])))
        centroid_distance = float(np.hypot(a['cx'] - b['cx'], a['cy'] - b['cy']))
        same_position = centroid_distance < 0.35 * max(np.sqrt(a['area_px']), np.sqrt(b['area_px']))
        if gap <= scale:
            kind = 'possivel_fragmento' if a['polarity'] == b['polarity'] else 'possivel_duplicata'
            a['quality_flags'].append(f'{kind}:{b["region_id"]}')
            b['quality_flags'].append(f'{kind}:{a["region_id"]}')
        elif same_position:
            a['quality_flags'].append(f'possivel_duplicata:{b["region_id"]}')
            b['quality_flags'].append(f'possivel_duplicata:{a["region_id"]}')
    for obj in objects:
        obj['quality_flags'] = sorted(set(obj['quality_flags']))
        obj['quality_status'] = 'suspeita' if obj['quality_flags'] else 'sem_alerta_heuristico'
        obj['global_noise'] = float(global_noise)
    return objects


def image_quality(objects):
    """Estado metodológico conservador, sem usar quantidade esperada de insertos.

    'provisoria' não significa validação: apenas há candidato(s) sem alerta
    heurístico. Nenhum caso recebe o rótulo de acurácia comprovada.
    """
    clear = sum(not obj.get('quality_flags') for obj in objects)
    if not objects:
        return {'estado': 'inconclusiva', 'motivos': ['nenhuma_regiao_detectada'],
                'regioes_sem_alerta': 0}
    if clear:
        return {'estado': 'provisoria', 'motivos': [],
                'regioes_sem_alerta': clear}
    reasons = ['nenhuma_regiao_sem_alerta_heuristico']
    flags = {flag.split(':', 1)[0] for obj in objects
             for flag in obj.get('quality_flags', [])}
    for flag in ('fundo_local_indisponivel', 'proximo_da_area_maxima',
                 'contraste_local_baixo', 'possivel_duplicata',
                 'possivel_fragmento', 'proximo_da_area_minima'):
        if flag in flags:
            reasons.append(flag)
    return {'estado': 'inconclusiva', 'motivos': reasons,
            'regioes_sem_alerta': 0}


def _bbox(obj):
    sl = obj['slice']
    return sl[0].start, sl[0].stop, sl[1].start, sl[1].stop


def _object_row(obj, crop_bbox):
    y0, y1, x0, x1 = _bbox(obj)
    return {
        'region_id': obj['region_id'], 'rank_bruto': obj['raw_rank'],
        'rank_corrigido': obj['corrected_rank'], 'polaridade': obj['polarity'],
        'centro_x_recorte_px': obj['cx'], 'centro_y_recorte_px': obj['cy'],
        'centro_x_imagem_px': obj['cx'] + crop_bbox['x'],
        'centro_y_imagem_px': obj['cy'] + crop_bbox['y'],
        'bbox_x_recorte_px': x0, 'bbox_y_recorte_px': y0,
        'bbox_largura_px': x1 - x0, 'bbox_altura_px': y1 - y0,
        'area_px': obj['area_px'], 'pixels_nucleo': obj['pixel_count'],
        'sinal_bruto': obj['mean'], 'desvio_padrao_roi': obj['std'],
        'fundo_local': obj['background'], 'desvio_padrao_fundo': obj['background_std'],
        'pixels_fundo': obj['background_pixels'], 'sinal_corrigido': obj['corrected'],
        'contraste_relativo_percentual': obj['relative_contrast'],
        'rsr': obj['rsr'], 'rcr': obj['rcr'], 'cnr_local_heuristico': obj['local_cnr'],
        'ruido_global_estimado': obj['global_noise'], 'qualidade': obj['quality_status'],
        'alertas': ';'.join(obj['quality_flags']),
    }


def export_results(output_dir, objects, labels, crop_bbox, run_info):
    """Escreve máscaras, coordenadas e tabela sem alterar os pixels DICOM."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rows = [_object_row(obj, crop_bbox) for obj in objects]
    fieldnames = list(rows[0]) if rows else [
        'region_id', 'rank_bruto', 'rank_corrigido', 'polaridade',
        'centro_x_recorte_px', 'centro_y_recorte_px', 'area_px', 'qualidade', 'alertas'
    ]
    for name in ('resultados.csv', 'coordenadas.csv'):
        with (destination / name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    metadata = dict(run_info)
    metadata.update({'crop_bbox': crop_bbox, 'objects': rows,
                     'schema_version': 1,
                     'nota': 'IDs são espaciais e independentes dos rankings de intensidade.'})
    with (destination / 'resultados.json').open('w', encoding='utf-8') as stream:
        json.dump(_json_value(metadata), stream, ensure_ascii=False, indent=2, allow_nan=False)
    np.savez_compressed(destination / 'mascaras.npz', labels=labels.astype(np.int32),
                        crop_bbox_yxwh=np.array([crop_bbox['y'], crop_bbox['x'], crop_bbox['height'], crop_bbox['width']], dtype=np.int32))
    return destination


def load_reference(path, expected_shape, crop_bbox):
    """Lê referência NPZ: labels 2D, no recorte ou na imagem DICOM inteira."""
    with np.load(path, allow_pickle=False) as archive:
        if 'labels' not in archive:
            raise ValueError('A referência NPZ deve conter um array 2D chamado labels.')
        labels = np.asarray(archive['labels'])
        stored_bbox = archive.get('crop_bbox_yxwh')
    if labels.ndim != 2:
        raise ValueError(f'Referência labels deve ser 2D; recebido {labels.shape}.')
    if labels.shape == expected_shape:
        return labels.astype(np.int32, copy=False)
    y, x, h, w = (crop_bbox[k] for k in ('y', 'x', 'height', 'width'))
    if labels.shape[0] >= y + h and labels.shape[1] >= x + w:
        return labels[y:y+h, x:x+w].astype(np.int32, copy=False)
    hint = '' if stored_bbox is None else f' Referência declara bbox {stored_bbox.tolist()}.'
    raise ValueError(f'Referência {labels.shape} não coincide com recorte {expected_shape}.{hint}')


def evaluate_instances(predicted, reference, iou_threshold=0.5):
    """Associa instâncias por IoU máximo (Hungarian) e devolve métricas objetivas."""
    if predicted.shape != reference.shape:
        raise ValueError('Máscaras automática e de referência devem ter a mesma forma.')
    if not 0 < iou_threshold <= 1:
        raise ValueError('iou_threshold deve estar no intervalo (0, 1].')
    pred_ids = np.unique(predicted); pred_ids = pred_ids[pred_ids > 0]
    ref_ids = np.unique(reference); ref_ids = ref_ids[ref_ids > 0]
    matrix = np.zeros((len(pred_ids), len(ref_ids)), dtype=float)
    for i, p in enumerate(pred_ids):
        pm = predicted == p
        for j, r in enumerate(ref_ids):
            rm = reference == r
            union = np.count_nonzero(pm | rm)
            matrix[i, j] = np.count_nonzero(pm & rm) / union if union else 0.0
    matches = []
    if matrix.size:
        ii, jj = linear_sum_assignment(-matrix)
        matches = [(int(pred_ids[i]), int(ref_ids[j]), float(matrix[i, j]))
                   for i, j in zip(ii, jj) if matrix[i, j] >= iou_threshold]
    matched_p = {m[0] for m in matches}; matched_r = {m[1] for m in matches}
    tp, fp, fn = len(matches), len(pred_ids) - len(matches), len(ref_ids) - len(matches)
    precision = tp / (tp + fp) if tp + fp else float('nan')
    recall = tp / (tp + fn) if tp + fn else float('nan')
    f1 = 2 * precision * recall / (precision + recall) if np.isfinite(precision + recall) and precision + recall else float('nan')
    pmask, rmask = predicted > 0, reference > 0
    inter = int(np.count_nonzero(pmask & rmask)); union = int(np.count_nonzero(pmask | rmask))
    matched_details = []
    for p, r, score in matches:
        py, px = np.nonzero(predicted == p)
        ry, rx = np.nonzero(reference == r)
        distance = float(np.hypot(px.mean() - rx.mean(), py.mean() - ry.mean()))
        matched_details.append({'automatico_id': p, 'referencia_id': r,
                                'iou': score, 'erro_centroide_px': distance})
    return {
        'iou_threshold': iou_threshold, 'predicted_regions': int(len(pred_ids)),
        'reference_regions': int(len(ref_ids)), 'true_positives': tp, 'false_positives': fp,
        'false_negatives': fn, 'precision': precision, 'recall': recall, 'f1': f1,
        'pixel_iou_foreground': inter / union if union else float('nan'),
        'pixel_dice_foreground': 2 * inter / (pmask.sum() + rmask.sum()) if pmask.sum() + rmask.sum() else float('nan'),
        'mean_iou_matches': float(np.mean([m[2] for m in matches])) if matches else float('nan'),
        'erro_centroide_medio_px': float(np.mean([m['erro_centroide_px'] for m in matched_details]))
        if matched_details else float('nan'),
        'matches': matched_details,
        'false_positive_ids': [int(x) for x in pred_ids if x not in matched_p],
        'false_negative_ids': [int(x) for x in ref_ids if x not in matched_r],
    }


def export_evaluation(output_dir, metrics):
    path = Path(output_dir) / 'avaliacao_referencia.json'
    with path.open('w', encoding='utf-8') as stream:
        json.dump(_json_value(metrics), stream, ensure_ascii=False, indent=2, allow_nan=False)
    return path
