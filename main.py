"""Entrada compatível: python3 main.py <DICOM> [opções]."""
import sys

from segmentador_fantomas.segmentacao import *  # reexporta a API usada em scripts antigos


if __name__ == '__main__':
    sys.exit(main())
