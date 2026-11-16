# radio2 — análise de fantomas radiográficos

O projeto detecta insertos em DICOMs 2D por contraste local e componentes
conectados, sem informar número, forma, tamanho, raio ou grade dos insertos.
Mede os pixels originais, o fundo local, o sinal corrigido experimental,
área, centroide, ruído, RSR e RCR. A detecção e a identificação física das
perfurações são etapas distintas.

## Começar

O ambiente atual é `venv/`. Para preparar outro ambiente Python no Debian,
instale `python3-venv` e `python3-tk`, crie um virtualenv e instale
`requirements.txt`.

```bash
cd ~/projects/radio2
venv/bin/python -m unittest discover -s tests -v
venv/bin/python main.py Crânio81_1 --sem-janela
venv/bin/python processar_lote.py --dicom-dir dicom \
  --output-dir resultados/novo_lote --sensibilidade 1.5
venv/bin/python interface.py
```

Cada execução gráfica gera `relatorio_<DICOM>.html` com quatro gráficos e
tabela. O lote cria um relatório por imagem. `--sem-grafico` imprime apenas
números. Para o relatório comparativo inspirado no TCC, use
`venv/bin/python -m radio2.gerar_resultados_tcc`; ele requer as exposições existentes
e usa o protocolo documentado em `docs/RECRIACAO_GRAFICOS_TCC.md`.

## Organização

- `dicom/`: nove imagens experimentais originais, sem extensão.
- `main.py`, `processar_lote.py`, `interface.py`: comandos de entrada preservados.
- `radio2/`: implementação do detector, processamento, revisão, avaliação,
  relatórios e curvas. Ferramentas auxiliares são executadas com
  `venv/bin/python -m radio2.NOME_DO_MODULO`.
- `referencias/`: anotações manuais independentes, iniciadas em branco.
- `resultados/`: saídas e versões históricas; veja `resultados/README.md`.
- `docs/`: protocolo, resultados, limites, código histórico e PDF do TCC.
- `simulacao_xrmc/`: experimento físico complementar, isolado do detector.
- `CONTEXTO_IC.md`: histórico técnico e decisões metodológicas.

Os DICOMs, resultados experimentais, referências, ambiente virtual, binários
locais do XRMC e o PDF do TCC são mantidos fora de uma publicação inicial no
GitHub pela [`.gitignore`](.gitignore). Para executar uma cópia do código,
forneça DICOMs próprios em `dicom/`; o comando também aceita um caminho
completo para um arquivo DICOM.

## Estado da pesquisa

Os sete DICOMs de Mão/Crânio/Tórax125_1 têm análise **provisória**.
Tórax125_2 e Tórax125_4 são **inconclusivos** com a sensibilidade 1,5:
nenhum candidato ficou sem alerta heurístico. Esses rótulos não são medidas
de acurácia. Faltam máscaras manuais independentes e um mapa de profundidades
conferido para calcular FP/FN, erro de segmentação e validar curvas físicas.
O sinal corrigido atual não replica literalmente a ROI 12 do TCC.

A interface permite selecionar cada objeto na própria revisão da máscara,
informar sua classe e profundidade e gerar curvas comparativas a partir do
CSV revisado. Ao salvar uma imagem de um lote, ela também transfere as
associações para exposições próximas da mesma técnica quando os centroides
correspondem de forma exclusiva; mapas manuais nos alvos são preservados.
O procedimento e os limites estão em
`docs/MAPEAMENTO_PROFUNDIDADES.md`.
