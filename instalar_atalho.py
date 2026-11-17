#!/usr/bin/env python3
"""Instala um atalho local que aponta para a pasta atual do projeto."""
import argparse
import os
from pathlib import Path


def install(destination=None):
    project = Path(__file__).resolve().parent
    launcher = project / 'iniciar_segmentador.sh'
    if destination is None:
        destination = Path.home() / '.local/share/applications/segmentador-fantomas.desktop'
    destination = Path(destination).expanduser()
    if '\n' in str(project) or '"' in str(project):
        raise ValueError('Caminho do projeto incompatível com o arquivo .desktop.')
    content = (f'[Desktop Entry]\nType=Application\nName=Segmentador de Fantomas\n'
               f'Comment=Analisar DICOMs e simulações de fantomas\n'
               f'Exec="{launcher}"\nPath={project}\n'
               'Terminal=false\nStartupNotify=true\nCategories=Science;Education;\n')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding='utf-8')
    os.chmod(destination, 0o755)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, help='Caminho alternativo para testar o atalho.')
    args = parser.parse_args()
    print(f'Atalho instalado em: {install(args.destino)}')


if __name__ == '__main__':
    main()
