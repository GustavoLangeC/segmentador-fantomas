"""Converte máscara manual TIFF/NPY em referência NPZ para avaliação."""
import argparse
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi


def read_mask(path):
    path = Path(path)
    if path.suffix.lower() == '.npy':
        mask = np.load(path, allow_pickle=False)
    elif path.suffix.lower() == '.npz':
        with np.load(path, allow_pickle=False) as archive:
            mask = archive['labels']
    else:
        mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if mask is None:
            raise ValueError('Não foi possível ler a máscara; use TIFF, NPY ou NPZ.')
        if mask.ndim == 3:
            raise ValueError('A máscara precisa ter um único canal de rótulos.')
    if mask.ndim != 2:
        raise ValueError(f'A máscara precisa ser 2D; recebido {mask.shape}.')
    return mask


def main():
    parser = argparse.ArgumentParser(description='Converte máscara manual em labels NPZ.')
    parser.add_argument('entrada', help='TIFF, NPY ou NPZ com máscara manual.')
    parser.add_argument('saida', help='Arquivo NPZ de referência.')
    parser.add_argument('--binaria', action='store_true',
                        help='Rotula componentes desconectados de uma máscara binária.')
    args = parser.parse_args()
    mask = read_mask(args.entrada)
    if args.binaria:
        labels, _ = ndi.label(mask > 0)
    else:
        labels = mask.astype(np.int32, copy=False)
    if np.any(labels < 0):
        raise ValueError('Rótulos devem ser inteiros não negativos.')
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.saida, labels=labels)
    print(f'Referência salva: {args.saida} | regiões: {len(np.unique(labels[labels > 0]))}')


if __name__ == '__main__':
    main()
