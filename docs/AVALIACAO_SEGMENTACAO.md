# Avaliação científica da segmentação automática

## O que o programa exporta

Execute, por exemplo:

```bash
venv/bin/python main.py Crânio81_1 --sem-grafico --output-dir resultados/cranio81_1_s15
```

O diretório contém:

- `mascaras.npz`: `labels` 2D, com `0` para fundo e um rótulo inteiro por ROI; também inclui `crop_bbox_yxwh` para recuperar as coordenadas na imagem original.
- `resultados.csv`: sinais medidos no DICOM bruto, fundo, sinal corrigido experimental, RSR, RCR, área, centroide, rankings e alertas.
- `coordenadas.csv`: tabela equivalente focada em coordenadas e caixas delimitadoras.
- `resultados.json`: metadados de execução e tabela em formato estruturado.

`region_id` (por exemplo, `R001`) é atribuído por ordem espacial de centroide e não é uma profundidade física. `rank_bruto` e `rank_corrigido` são campos independentes; nenhum dos três identifica a perfuração física.

## Máscara manual e comparação

A opção **Anotar referência** da interface (ou
`venv/bin/python -m radio2.anotar_referencia dicom/Crânio81_1 referencias/Crânio81_1`)
inicia uma matriz de rótulos vazia sobre o DICOM inteiro, sem importar máscaras
do detector. Cada salvamento cria uma versão NPZ e um JSON com proveniência.
Uma versão salva ainda precisa de conferência independente antes de servir
como referência científica.

A referência deve ser um `.npz` com um array 2D inteiro chamado `labels`: zero é fundo, cada ROI manual recebe um valor positivo distinto. Ela pode ter o mesmo tamanho do recorte exportado ou o tamanho total do DICOM; neste último caso o programa aplica o bbox do recorte automaticamente.

Para converter uma máscara manual TIFF/NPY exportada do ImageJ, use `converter_referencia.py`. Se a imagem for binária com ROIs desconectadas, `--binaria` cria um rótulo por componente:

```bash
venv/bin/python -m radio2.converter_referencia referencias/cranio81_1.tif \
  referencias/cranio81_1_manual.npz --binaria
```

Exemplo de avaliação:

```bash
venv/bin/python main.py Crânio81_1 --sem-grafico \
  --output-dir resultados/cranio81_1_s15 \
  --referencia referencias/cranio81_1_manual.npz --iou-minimo 0.5
```

O arquivo `avaliacao_referencia.json` registra TP, FP, FN, precisão,
revocação, F1, IoU/Dice de primeiro plano, associações por IoU e erro
euclidiano do centroide em pixels para cada par associado e sua média.
A associação usa otimização global por IoU; a máscara manual não influencia
a detecção. Sem referência manual independente, essas métricas não estimam
acurácia científica.

## Alertas de qualidade

Os alertas são heurísticos e não constituem probabilidade calibrada ou decisão clínica. Eles sinalizam contraste local baixo, fundo indisponível, região próxima dos limites de área e pares com proximidade de caixa/centroide compatível com fragmento ou duplicata. Não há descarte automático nesta versão.

## Limitações atuais

- Sem referência manual, as contagens e os alertas não permitem afirmar acurácia.
- A correção radiométrica permanece a adaptação experimental `S_bruto/fundo_local * mediana(fundos locais)`; ela não equivale ao fundo da ROI 12 do TCC e não prova remoção do efeito anódico.
- RSR e RCR são calculadas para cada máscara detectada a partir do sinal bruto e do anel de fundo. Sua validade depende da qualidade da máscara e desse anel.
- A referência manual precisa estar alinhada à matriz DICOM/recorte; o programa não faz registro geométrico entre imagens diferentes.
- Os critérios de fragmento/duplicata apenas sinalizam candidatos. A decisão de mesclar ou rejeitar exige validação contra referência.
- O recorte externo e os limiares relativos ainda devem ser testados em fantomas com outras escalas, contrastes, formas e disposições.
