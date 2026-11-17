"""Confere formato, vínculo e integridade básica de uma máscara manual.

Esta checagem não julga se o contorno está correto; isso exige revisão humana.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pydicom
from scipy import ndimage as ndi


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate(dicom_path, reference_path):
    dicom_path, reference_path = Path(dicom_path), Path(reference_path)
    header = pydicom.dcmread(dicom_path, stop_before_pixels=True)
    expected = (int(header.Rows), int(header.Columns))
    with np.load(reference_path, allow_pickle=False) as archive:
        if 'labels' not in archive:
            raise ValueError('NPZ sem array labels.')
        labels = np.asarray(archive['labels'])
    if labels.ndim != 2 or labels.shape != expected:
        raise ValueError(f'Máscara {labels.shape} não coincide com DICOM {expected}.')
    if not np.issubdtype(labels.dtype, np.integer) or np.any(labels < 0):
        raise ValueError('Rótulos devem ser inteiros não negativos.')
    ids = np.unique(labels[labels > 0])
    if not len(ids):
        raise ValueError('Máscara sem regiões anotadas.')
    digest = sha256(dicom_path)
    sidecar = reference_path.with_suffix('.json')
    provenance = 'não disponível'
    if sidecar.exists():
        metadata = json.loads(sidecar.read_text(encoding='utf-8'))
        if metadata.get('dicom_sha256') and metadata['dicom_sha256'] != digest:
            raise ValueError('SHA-256 do DICOM difere do registro da anotação.')
        provenance = metadata.get('origem', 'não informada')
    objects = []
    for id_ in ids:
        mask = labels == id_
        _, components = ndi.label(mask)
        ys, xs = np.nonzero(mask)
        objects.append({'id': int(id_), 'area_px': int(mask.sum()),
                        'centro_x_px': float(xs.mean()), 'centro_y_px': float(ys.mean()),
                        'componentes_conectados': int(components)})
    return {'dicom': str(dicom_path.resolve()), 'dicom_sha256': digest,
            'referencia': str(reference_path.resolve()), 'dimensoes_yx': list(expected),
            'origem': provenance, 'regioes': len(objects),
            'pixels_anotados': int(np.count_nonzero(labels)), 'objetos': objects,
            'nota': 'Integridade de arquivo conferida; acurácia do contorno e profundidades exigem revisão independente.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dicom', type=Path)
    parser.add_argument('referencia', type=Path)
    parser.add_argument('--saida', type=Path, help='JSON de conferência; sem esta opção imprime no terminal.')
    args = parser.parse_args()
    result = validate(args.dicom, args.referencia)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(output, encoding='utf-8')
        print(f'Conferência salva em: {args.saida}')
    else:
        print(output)


if __name__ == '__main__':
    main()
