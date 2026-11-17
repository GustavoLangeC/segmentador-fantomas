"""Compatibilidade para comandos antigos ``python -m radio2.modulo``.

O código atual reside em :mod:`segmentador_fantomas`. A busca por submódulos
usa o diretório novo sem duplicar arquivos nem alterar a CLI histórica.
"""
from segmentador_fantomas import __path__ as _current_path

__path__ = _current_path
