# Estado de qualidade por imagem e erro de centroide

**Data:** 16 de novembro de 2026.

## Mudança

Depois dos alertas por objeto, `image_quality` marca a análise como
`inconclusiva` se não há região detectada ou se **todas** as regiões têm
alertas heurísticos. Com ao menos uma região sem alerta, o estado é
`provisoria`, nunca "validada". A regra não recebe número esperado, grade,
forma ou tamanho dos insertos. A execução do software continua com
`status=concluido`; `qualidade_analise` é campo distinto no JSON e no resumo
do lote. Nenhuma região suspeita é apagada, permitindo revisão posterior.

`evaluate_instances` agora informa erro euclidiano do centroide em pixels
para cada par associado por IoU e a média desses erros. Isso só tem
significado científico com uma máscara manual independente.

## Antes/depois reprodutível

```bash
cd ~/projects/radio2
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m radio2.processar_lote --dicom-dir dicom \
  --output-dir /tmp/radio2_qualidade_2026-11-16 --sensibilidade 1.5
```

Comparação feita com `resultados/lote_demonstracao_2026-11-16`, também em
sensibilidade 1,5. Para os nove DICOMs, `resultados.csv` foi idêntico linha a
linha e as matrizes `labels` e `crop_bbox_yxwh` dos NPZ foram iguais.

| Imagem | Regiões | Com alerta | Estado novo |
| --- | ---: | ---: | --- |
| Crânio81_1 | 24 | 2 | provisória |
| Crânio81_2 | 23 | 1 | provisória |
| Crânio81_4 | 24 | 2 | provisória |
| Mão46_1 | 24 | 4 | provisória |
| Mão46_2 | 24 | 3 | provisória |
| Mão46_4 | 23 | 1 | provisória |
| Tórax125_1 | 24 | 2 | provisória |
| Tórax125_2 | 5 | 5 | **inconclusiva** |
| Tórax125_4 | 1 | 1 | **inconclusiva** |

Tórax125_2 apresenta avisos de fundo indisponível, candidato próximo da área
máxima, duplicação e contraste local baixo. Tórax125_4 tem contraste local
baixo. Os estados são avisos conservadores, não estimativas calibradas de
probabilidade. Não há TP/FP/FN mensurados por falta de máscaras manuais.
Pico de RAM do lote completo não foi medido. Em execução isolada de
`Crânio81_1 --sem-janela`, um monitor de `/proc/<pid>/status` observou
`VmHWM=202496 kB` em 5,24 s. Antes desta mudança, uma execução do mesmo
arquivo e opção registrou 202556 kB em 5,35 s. Esses dois pontos não
demonstram tendência estatística, mas não indicam regressão grande de memória.

O teste sintético deslocou um objeto por (4,3) px e verificou erro de
centroide de 5 px. Sete testes sintéticos passaram após a inclusão do editor
de referência em branco e do mapeamento físico informado pelo usuário. A interface Tkinter
não foi testada visualmente neste ambiente.

Como teste de integração de exportação, `Crânio81_1` foi avaliado contra sua
**própria** máscara automática, produzindo 24 associações e erro médio de
centroide 0 px. Esse teste verifica apenas leitura e escrita do campo novo;
não é avaliação de acurácia independente.
