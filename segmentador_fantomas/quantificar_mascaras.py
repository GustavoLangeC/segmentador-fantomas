"""Recalcula resultados para máscaras revisadas, usando pixels DICOM brutos."""
import argparse
import json
from pathlib import Path

import numpy as np
import pydicom
from scipy import ndimage as ndi

from .avaliacao import export_results, image_quality, object_quality
from .segmentacao import InsertoDetector, show_results
from .relatorio_individual import escrever_relatorio


def quantificar(dicom, automatico, mascara, saida):
    automatico, mascara, saida = map(Path, (automatico, mascara, saida))
    with (automatico / 'resultados.json').open(encoding='utf-8') as stream:
        previous = json.load(stream)
    recorded = Path(previous['dicom'])
    if recorded.name != Path(dicom).name or (recorded.is_absolute() and recorded.resolve() != Path(dicom).resolve()):
        raise ValueError('O DICOM informado não corresponde à execução automática.')
    bbox = previous['crop_bbox']
    with np.load(automatico / 'mascaras.npz', allow_pickle=False) as data:
        original = data['labels']
        original_bbox = data['crop_bbox_yxwh']
    with np.load(mascara, allow_pickle=False) as data:
        labels = data['labels']
        edited_bbox = data['crop_bbox_yxwh']
    if labels.shape != original.shape or not np.array_equal(edited_bbox, original_bbox):
        raise ValueError('Máscara revisada e resultado automático têm recortes diferentes.')
    if not np.issubdtype(labels.dtype, np.integer) or np.any(labels < 0):
        raise ValueError('Rótulos devem ser inteiros não negativos.')
    ds = pydicom.dcmread(dicom)
    raw = ds.pixel_array
    y, x, h, w = map(int, original_bbox)
    if raw.ndim != 2 or y + h > raw.shape[0] or x + w > raw.shape[1]:
        raise ValueError('Recorte não corresponde ao DICOM informado.')
    crop = raw[y:y+h, x:x+w]
    margin = max(8, int(min(crop.shape) * 0.035))
    phantom_mask = np.zeros(crop.shape, dtype=bool)
    mx, my = max(2, int(0.012*w)), max(2, int(0.012*h))
    phantom_mask[my:h-my, mx:w-mx] = True
    inside = ndi.binary_erosion(phantom_mask, iterations=margin)
    occupied = labels > 0
    prior = {int(row['region_id'][1:]): row for row in previous['objects']}
    objects = []
    for label_id in np.unique(labels):
        if label_id == 0:
            continue
        yy, xx = np.where(labels == label_id)
        sl = np.s_[yy.min():yy.max()+1, xx.min():xx.max()+1]
        mask = labels[sl] == label_id
        core = ndi.binary_erosion(mask, iterations=2)
        if core.sum() < max(9, 0.2 * mask.sum()):
            core = mask
        values = crop[sl][core].astype(np.float64)
        obj = {'slice': sl, 'mask': mask, 'area_px': int(mask.sum()),
               'cx': float(xx.mean()), 'cy': float(yy.mean()),
               'mean': float(values.mean()), 'std': float(values.std()),
               'pixel_count': int(values.size), 'source_label': int(label_id)}
        bg, bg_std, bg_count = InsertoDetector.local_background(
            crop, inside, occupied, obj)
        obj.update(background=bg, background_std=bg_std,
                   background_pixels=bg_count)
        prior_row = prior.get(int(label_id))
        obj['polarity'] = (prior_row['polaridade'] if prior_row else
                           ('escuro' if np.isfinite(bg) and obj['mean'] < bg else 'claro'))
        objects.append(obj)
    ref_values = [o['background'] for o in objects if np.isfinite(o['background']) and o['background'] > 0]
    reference = float(np.median(ref_values)) if ref_values else float('nan')
    noise = float(previous['objects'][0]['ruido_global_estimado']) if previous['objects'] else float('nan')
    for obj in objects:
        bg = obj['background']
        obj['corrected'] = obj['mean'] / bg * reference if np.isfinite(bg) and bg > 0 else float('nan')
        obj['relative_contrast'] = 100 * (obj['mean'] / bg - 1) if np.isfinite(bg) and bg > 0 else float('nan')
        obj['global_noise'] = noise
    for rank, obj in enumerate(sorted(objects, key=lambda o: (-o['mean'], o['cy'], o['cx'])), 1):
        obj['raw_rank'] = rank
    for rank, obj in enumerate(sorted(objects, key=lambda o: (not np.isfinite(o['corrected']),
                                                            -o['corrected'] if np.isfinite(o['corrected']) else 0)), 1):
        obj['corrected_rank'] = rank
    objects.sort(key=lambda o: (o['cy'], o['cx']))
    normalized = np.zeros(labels.shape, dtype=np.int32)
    for index, obj in enumerate(objects, 1):
        obj['id'] = index
        obj['region_id'] = f'R{index:03d}'
        normalized[obj['slice']][obj['mask']] = index
    min_area = max(25, int(inside.sum() * 0.00018))
    max_area = int(inside.sum() * 0.15)
    if objects:
        object_quality(objects, normalized, noise, min_area, max_area)
    assessment = image_quality(objects)
    saida.mkdir(parents=True, exist_ok=True)
    export_results(saida, objects, normalized, bbox,
                   {'dicom': str(dicom), 'source': 'mascara_revisada',
                    'mascara_editada': str(mascara),
                    'qualidade_analise': assessment,
                    'correction_note': previous.get('correction_note', '')})
    changes = {'pixels_alterados': int(np.count_nonzero(labels != original)),
               'pixels_primeiro_plano_adicionados': int(np.count_nonzero((labels > 0) & (original == 0))),
               'pixels_primeiro_plano_removidos': int(np.count_nonzero((labels == 0) & (original > 0))),
               'regioes_revisadas': len(objects), 'rotulos_origem':
               {o['region_id']: o['source_label'] for o in objects}}
    (saida / 'alteracoes.json').write_text(json.dumps(changes, indent=2, ensure_ascii=False), encoding='utf-8')
    show_results(crop, objects, normalized, saida / 'resultado_revisado.png', show_window=False)
    escrever_relatorio(saida / 'relatorio_revisado.html', dicom, objects,
                       previous.get('sensitivity'),
                       imagem_path=saida / 'resultado_revisado.png')
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dicom', type=Path)
    parser.add_argument('automatico', type=Path)
    parser.add_argument('mascara', type=Path)
    parser.add_argument('saida', type=Path)
    args = parser.parse_args()
    print(json.dumps(quantificar(args.dicom, args.automatico, args.mascara, args.saida),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
