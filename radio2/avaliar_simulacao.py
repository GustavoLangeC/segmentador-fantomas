"""Avalia uma imagem XRMC NPY com o mesmo detector usado para DICOMs.

A geometria conhecida entra apenas pela referência NPZ, depois da detecção.
Os valores float64 originais são usados nas medições; float32 é empregado
internamente pelo detector somente para localizar regiões.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

from .avaliacao import (evaluate_instances, export_evaluation, export_results,
                        image_quality, load_reference, object_quality)
from .segmentacao import InsertoDetector, PhantomSegmenter


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _preview(image, predicted, reference, path):
    low, high = np.percentile(image, (1, 99))
    if high <= low:
        high = low + 1
    gray = np.clip((image.astype(np.float32) - low) * (255 / (high - low)),
                   0, 255).astype(np.uint8)
    raw = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    marked = raw.copy()
    tp = (predicted > 0) & (reference > 0)
    fp = (predicted > 0) & (reference == 0)
    fn = (predicted == 0) & (reference > 0)
    for mask, color in ((tp, (0, 190, 0)), (fp, (0, 0, 230)),
                        (fn, (220, 90, 0))):
        marked[mask] = (0.4 * marked[mask] + 0.6 * np.array(color)).astype(np.uint8)
    panels = np.concatenate((raw, marked), axis=1)
    panels = cv2.resize(panels, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    if not cv2.imwrite(str(path), panels):
        raise RuntimeError(f'Não foi possível salvar a prévia: {path}')


def _report(path, image, reference, objects, metrics, quality, bound):
    def fmt(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return '—'
        return f'{number:.3f}' if np.isfinite(number) else '—'

    rows = ''.join(
        '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            html.escape(obj['region_id']), obj['area_px'], fmt(obj['mean']),
            fmt(obj['background']), fmt(obj['corrected']))
        for obj in objects
    )
    note = ('Referência vinculada ao SHA-256 da imagem.' if bound else
            'A referência não possui manifesto de vínculo; confira se corresponde à imagem.')
    page = f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Avaliação de simulação — {html.escape(image.name)}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:auto;padding:24px;color:#243746}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccd9df;padding:6px 10px;text-align:right}}
th:first-child,td:first-child{{text-align:left}}img{{max-width:100%;image-rendering:pixelated}}</style>
<h1>Avaliação de simulação — {html.escape(image.name)}</h1>
<p>Referência: {html.escape(reference.name)}. {note}</p>
<p>Estado heurístico da análise: {html.escape(quality['estado'])}. Essa classificação não é validação científica.</p>
<table><tr><th>TP</th><th>FP</th><th>FN</th><th>IoU por pixel</th><th>IoU da associação</th></tr>
<tr><td>{metrics['true_positives']}</td><td>{metrics['false_positives']}</td>
<td>{metrics['false_negatives']}</td><td>{fmt(metrics['pixel_iou_foreground'])}</td>
<td>{fmt(metrics['mean_iou_matches'])}</td></tr></table>
<p>Associação de instâncias: IoU mínimo {fmt(metrics['iou_threshold'])}.
Referência calculada da geometria ideal do cenário, com raios centrais e centros de pixel;
a borda física simulada pode diferir por amostragem e penumbra. Este único cenário não
valida a segmentação em DICOMs clínicos ou outros fantomas.</p>
<p><a href="comparacao.png">Comparação visual</a> · <a href="avaliacao_referencia.json">Métricas completas</a>
· <a href="resultados.csv">Medições CSV</a></p>
<img src="comparacao.png" alt="Imagem original à esquerda; acertos verdes, falsos positivos vermelhos e falsos negativos azuis à direita">
<p>Esquerda: sinal simulado original em escala de exibição. Direita: verde = sobreposição,
vermelho = detecção fora da referência, azul = referência não detectada.</p>
<h2>Medições nos valores originais</h2><table><tr><th>ID</th><th>Área (px)</th>
<th>Sinal bruto</th><th>Fundo local</th><th>Sinal corrigido experimental</th></tr>{rows}</table>
<p>O sinal corrigido usa uma adaptação experimental baseada na mediana dos fundos locais;
ele não identifica profundidade física.</p></html>'''
    path.write_text(page, encoding='utf-8')


def run(image_path, reference_path, output_dir, sensitivity=1.5, min_area=0,
        iou_threshold=0.5):
    image_path, reference_path, output_dir = map(Path, (image_path, reference_path, output_dir))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f'Diretório de saída já contém dados: {output_dir}')
    image = np.load(image_path, allow_pickle=False)
    if image.ndim != 2 or not np.issubdtype(image.dtype, np.number):
        raise ValueError('A imagem NPY deve ser uma matriz numérica 2D.')
    if not np.isfinite(image).all():
        raise ValueError('A imagem NPY contém valores não finitos.')
    sidecar = reference_path.with_suffix('.json')
    bound = False
    if sidecar.exists():
        metadata = json.loads(sidecar.read_text(encoding='utf-8'))
        if metadata.get('image_sha256') != _sha256(image_path):
            raise ValueError('A referência não corresponde ao SHA-256 da imagem NPY.')
        bound = True

    segmenter = PhantomSegmenter()
    crop, phantom_mask = segmenter.detect(image)
    objects, labels = InsertoDetector(sensitivity, min_area).detect(crop, phantom_mask)
    reference = load_reference(reference_path, labels.shape, segmenter.last_bbox)
    metrics = evaluate_instances(labels, reference, iou_threshold)
    inner_margin = max(8, int(min(crop.shape) * 0.035))
    inside_count = int(np.count_nonzero(ndi.binary_erosion(phantom_mask, iterations=inner_margin)))
    detector_min = min_area or max(25, int(inside_count * 0.00018))
    detector_max = int(inside_count * 0.15)
    if objects:
        noise = next((obj['global_noise'] for obj in objects if 'global_noise' in obj), float('nan'))
        object_quality(objects, labels, noise, detector_min, detector_max)
    quality = image_quality(objects)
    run_info = {
        'source_type': 'simulacao_xrmc', 'source_image': str(image_path.resolve()),
        'source_image_sha256': _sha256(image_path),
        'reference_file': str(reference_path.resolve()),
        'reference_bound_to_image': bound, 'sensitivity': sensitivity,
        'min_area_argument': min_area, 'detected_regions': len(objects),
        'qualidade_analise': quality,
        'correction_note': 'S_corrigido=(S_bruto/fundo_local)*mediana(fundos locais válidos); adaptação experimental.',
    }
    export_results(output_dir, objects, labels, segmenter.last_bbox, run_info)
    export_evaluation(output_dir, metrics)
    _preview(crop, labels, reference, output_dir / 'comparacao.png')
    _report(output_dir / 'relatorio_simulacao.html', image_path, reference_path,
            objects, metrics, quality, bound)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imagem', type=Path, required=True, help='NPY com os valores originais do XRMC.')
    parser.add_argument('--referencia', type=Path, required=True, help='NPZ com labels gerado pela simulação.')
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--sensibilidade', type=float, default=1.5)
    parser.add_argument('--min-area', type=int, default=0)
    parser.add_argument('--iou-minimo', type=float, default=0.5)
    args = parser.parse_args()
    metrics = run(args.imagem, args.referencia, args.saida, args.sensibilidade,
                  args.min_area, args.iou_minimo)
    print('TP={true_positives} FP={false_positives} FN={false_negatives} '
          'IoU_pixel={pixel_iou_foreground:.3f}'.format(**metrics))
    print(f'Relatório: {args.saida / "relatorio_simulacao.html"}')


if __name__ == '__main__':
    main()
