"""Reaproveita associações físicas entre exposições do mesmo grupo experimental.

A transferência ocorre depois da detecção, com correspondência espacial 1:1.
Ela não fornece posições, número ou geometria ao segmentador.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pydicom
from scipy.optimize import linear_sum_assignment

from .mapear_profundidades import (CLASSES, generate_single_curves,
                                    latest_measurements, load_current_map,
                                    read_rows, save_mapping)


AUTO_ORIGIN = 'transferencia_espacial_automatica'


def group_key(path):
    match = re.fullmatch(r'(.+)_([0-9]+)', Path(path).stem)
    return match.group(1) if match else None


def compatible_images(source, target):
    """Recusa imagens com dimensões muito diferentes sem ler pixel_array."""
    first = pydicom.dcmread(source, stop_before_pixels=True)
    second = pydicom.dcmread(target, stop_before_pixels=True)
    return all(abs(int(getattr(first, field)) - int(getattr(second, field))) /
               max(int(getattr(first, field)), int(getattr(second, field))) <= .05
               for field in ('Rows', 'Columns'))


def _typical_spacing(points):
    if len(points) < 2:
        return 0.0
    distances = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    return float(np.median(distances.min(axis=1)))


def match_positions(source_rows, target_rows):
    """Associa centroides próximos e únicos; não usa ordem dos IDs nem grade."""
    source = np.array([[float(row['centro_x_imagem_px']),
                        float(row['centro_y_imagem_px'])] for row in source_rows])
    target = np.array([[float(row['centro_x_imagem_px']),
                        float(row['centro_y_imagem_px'])] for row in target_rows])
    if len(source) < 2 or len(target) < 2:
        return [], 0.0
    threshold = min(25.0, .30 * min(_typical_spacing(source),
                                   _typical_spacing(target)))
    if threshold <= 0:
        return [], 0.0
    distances = np.linalg.norm(source[:, None, :] - target[None, :, :], axis=2)
    origins, destinations = linear_sum_assignment(distances)
    matches = []
    for i, j in zip(origins, destinations):
        distance = float(distances[i, j])
        if (distance <= threshold and j == int(np.argmin(distances[i])) and
                i == int(np.argmin(distances[:, j])) and
                np.count_nonzero(distances[i] <= threshold) == 1 and
                np.count_nonzero(distances[:, j] <= threshold) == 1):
            matches.append((source_rows[i]['region_id'], target_rows[j]['region_id'],
                            round(distance, 3)))
    return matches, round(threshold, 3)


def _manual_map_exists(run_dir):
    candidates = [run_dir, *(run_dir / 'revisoes').glob('revisao_*')]
    for folder in candidates:
        if not (folder / 'mapa_profundidades.json').is_file():
            continue
        mapping = load_current_map(folder)
        if mapping.get('origem') != AUTO_ORIGIN:
            return True
    return False


def _transfer_target(item, source_item, source_run, source_result,
                     source_map, source_rows, source_entries):
    target_run = Path(item['diretorio']).resolve()
    entry = {'imagem': Path(item['arquivo']).name,
             'execucao': str(target_run), 'estado': 'omitido'}
    if item['status'] != 'concluido':
        entry['motivo'] = 'processamento não concluído'; return entry
    target_result = latest_measurements(target_run)
    target_meta = json.loads((target_result / 'resultados.json').read_text(encoding='utf-8'))
    target_rows = read_rows(target_result)
    if (target_meta.get('qualidade_analise', {}).get('estado') == 'inconclusiva' or
            all(row['alertas'] for row in target_rows)):
        entry['motivo'] = 'análise inconclusiva'; return entry
    if not compatible_images(source_item['arquivo'], item['arquivo']):
        entry['motivo'] = 'dimensões DICOM incompatíveis'; return entry
    if _manual_map_exists(target_run):
        entry['motivo'] = 'mapa já editado pelo usuário'; return entry
    current = load_current_map(target_result)
    if current and current.get('origem') == AUTO_ORIGIN:
        previous = current.get('proveniencia_transferencia', {})
        if previous.get('fonte_execucao') != str(source_run):
            entry['motivo'] = 'mapa transferido de outra origem'; return entry
    matches, threshold = match_positions(source_rows, target_rows)
    if len(matches) < 2:
        entry['motivo'] = 'menos de duas posições correspondentes'; return entry
    assignments = {row['region_id']:
                   {'classe': CLASSES[0], 'profundidade_mm': ''}
                   for row in target_rows}
    copied = []
    for source_id, target_id, distance in matches:
        source_entry = source_entries[source_id]
        if source_entry['classe'] == CLASSES[0]:
            continue
        assignments[target_id] = {'classe': source_entry['classe'],
                                  'profundidade_mm': source_entry['profundidade_mm']}
        copied.append({'origem_id': source_id, 'alvo_id': target_id,
                       'distancia_px': distance})
    if not copied:
        entry['motivo'] = 'nenhuma região classificada teve correspondência'; return entry
    provenance = {'fonte_execucao': str(source_run),
                  'fonte_resultado': str(source_result),
                  'fonte_csv_sha256': source_map['resultados_csv_sha256'],
                  'distancia_limite_px': threshold, 'pares_copiados': copied,
                  'sem_correspondencia_origem': sorted(
                      set(source_entries) - {a for a, _, _ in matches}),
                  'sem_correspondencia_alvo': sorted(
                      set(assignments) - {b for _, b, _ in matches}),
                  'conferencia_visual_pendente': True}
    notes = f'Transferido de {source_result}; conferir posições e contornos nesta exposição.'
    path, mapping = save_mapping(target_result, assignments, notes,
                                 origin=AUTO_ORIGIN, provenance=provenance)
    entry.update(estado='preenchido', resultado=str(target_result), mapa=str(path),
                 correspondencias=len(matches), classes_copiadas=len(copied),
                 insertos_copiados=mapping['contagem']['inserto'],
                 sem_correspondencia_origem=provenance['sem_correspondencia_origem'],
                 sem_correspondencia_alvo=provenance['sem_correspondencia_alvo'])
    if mapping['contagem']['inserto']:
        try:
            generate_single_curves(target_result)
        except Exception as exc:
            entry['aviso_curvas'] = str(exc)
    return entry


def transfer_group(source_run, source_result):
    """Cria mapas provisórios nos pares do lote sem sobrescrever mapas manuais."""
    source_run, source_result = Path(source_run).resolve(), Path(source_result).resolve()
    summary_path = source_run.parent / 'resumo_lote.json'
    if not summary_path.is_file():
        return None
    if latest_measurements(source_run) != source_result:
        raise ValueError('A origem precisa ser a versão mais recente das medições.')
    source_map = load_current_map(source_result)
    if source_map is None or source_map.get('origem') != 'associacao_fisica_informada_pelo_usuario':
        return None
    if source_map['contagem'].get('inserto', 0) < 1:
        return None
    source_meta = json.loads((source_result / 'resultados.json').read_text(encoding='utf-8'))
    source_rows = read_rows(source_result)
    if (source_meta.get('qualidade_analise', {}).get('estado') == 'inconclusiva' or
            all(row['alertas'] for row in source_rows)):
        return None
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    source_item = next((item for item in summary
                        if Path(item['diretorio']).resolve() == source_run), None)
    if source_item is None:
        return None
    group = group_key(source_item['arquivo'])
    if group is None:
        return None
    source_entries = {entry['region_id']: entry for entry in source_map['entries']}
    report = {'grupo': group, 'origem': str(source_result),
              'origem_csv_sha256': source_map['resultados_csv_sha256'],
              'metodo': 'centroides_proximos_exclusivos_sem_grade',
              'validacao_independente': False, 'alvos': []}
    for item in summary:
        target_run = Path(item['diretorio']).resolve()
        if target_run == source_run or group_key(item['arquivo']) != group:
            continue
        try:
            entry = _transfer_target(item, source_item, source_run, source_result,
                                     source_map, source_rows, source_entries)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            entry = {'imagem': Path(item['arquivo']).name,
                     'execucao': str(target_run), 'estado': 'omitido',
                     'motivo': f'erro ao conferir alvo: {exc}'}
        report['alvos'].append(entry)
    (source_result / 'transferencia_grupo.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origem', type=Path, help='Pasta do resultado mapeado, preferencialmente revisão mais recente.')
    args = parser.parse_args()
    source_result = args.origem.resolve()
    source_run = (source_result.parent.parent if source_result.parent.name == 'revisoes'
                  else source_result)
    report = transfer_group(source_run, source_result)
    print(json.dumps(report or {'estado': 'sem grupo ou mapa manual utilizável'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
