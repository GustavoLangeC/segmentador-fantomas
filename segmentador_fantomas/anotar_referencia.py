"""Abre anotação manual vazia, sem mostrar rótulos produzidos pelo detector."""
import argparse
from pathlib import Path
import tkinter as tk

from .editor_mascaras import Editor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dicom', type=Path)
    parser.add_argument('saida', type=Path)
    args = parser.parse_args()
    dicom = args.dicom.resolve()
    if not dicom.is_file():
        parser.error(f'DICOM não encontrado: {dicom}')
    root = tk.Tk()
    Editor(root, dicom, None, args.saida.resolve())
    root.mainloop()


if __name__ == '__main__':
    main()
