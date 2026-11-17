# Organização do segmentador-fantomas

**Atualizado em 16 de novembro de 2026.**

| Caminho | Conteúdo |
| --- | --- |
| `main.py` | Comando principal de análise de um DICOM. |
| `processar_lote.py` | Comando de processamento de lote. |
| `interface.py` | Entrada da interface gráfica. O atalho `.desktop` local não é publicado. |
| `iniciar_segmentador.sh`, `instalar_atalho.py` | Iniciam a interface e criam o atalho local do menu. |
| `segmentador_fantomas/` | Detector, medições, avaliação, revisão e geradores de relatórios. |
| `radio2/` | Compatibilidade para comandos antigos, sem duplicar o código. |
| `dicom/` | DICOMs originais. |
| `referencias/` | Referências manuais independentes, quando preenchidas. |
| `resultados/lote/` | Lote iniciado na interface, com revisões. |
| `resultados/lote_demonstracao_2026-11-16/` | Nove execuções usadas como comparação. |
| `resultados/recriacao_tcc_2026-11-16/` | Gráficos e tabelas análogos ao TCC. |
| `resultados/historico/` | Saídas antigas preservadas. |
| `docs/historico_codigo/` | Versão anterior do código principal. |
| `../simulacao-xrmc/` | Repositório irmão: simulação XRMC e referência geométrica. |

Comandos usuais:

```bash
venv/bin/python main.py Crânio81_1 --sem-janela
venv/bin/python processar_lote.py --dicom-dir dicom --output-dir resultados/novo_lote
venv/bin/python interface.py
venv/bin/python -m segmentador_fantomas.gerar_resultados_tcc --help
venv/bin/python -m segmentador_fantomas.mapear_profundidades --help
venv/bin/python -m segmentador_fantomas.avaliar_simulacao --help
venv/bin/python -m segmentador_fantomas.benchmark_simulacao --help
```

As ferramentas auxiliares que antes estavam soltas na raiz são executadas
com `-m segmentador_fantomas.NOME_DO_MODULO`. Os caminhos dos lotes ativos não mudaram.
O histórico detalhado de testes, limitações e dados permanece em
`CONTEXTO_IC.md`.
