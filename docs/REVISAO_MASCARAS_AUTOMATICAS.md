# Rascunhos automáticos de máscaras — 16 de novembro de 2026

O diretório `resultados/historico/revisao_automatica/` contém um rascunho por DICOM.
Cada pasta tem `rascunho_automatico.npz`, `rascunho_rotulos.tif`,
`imagem_recortada_bruta.tif`, `revisao.png`, `fila.csv` e `resumo.json`.
Os dois TIFFs têm o mesmo tamanho e podem ser abertos no ImageJ: um contém os
pixels originais do recorte, o outro contém rótulos inteiros para correção.
A máscara NPZ é cópia da saída do detector com sensibilidade
1,5. A execução com 1,2 é usada para medir estabilidade e revelar regiões
adicionais; ela não constitui uma segunda anotação humana ou referência
independente.

Na prévia: verde indica máscara estável sem alerta; laranja, mudança relevante
entre parâmetros; vermelho, alerta de qualidade; magenta `A<n>` indica região
encontrada somente com sensibilidade 1,2. As cores servem apenas para priorizar
a revisão. Toda a imagem deve ser examinada ao menos uma vez para descobrir
possíveis falsos negativos ausentes das duas execuções.

Para reproduzir a análise de um DICOM:

```bash
venv/bin/python main.py Crânio81_1 --sem-grafico --sensibilidade 1.2 \
  --output-dir resultados/historico/rascunho_sensibilidade_1.2/Crânio81_1
venv/bin/python -m segmentador_fantomas.preparar_revisao_mascaras dicom/Crânio81_1 \
  resultados/historico/linha_base_2026-11-16_sensibilidade_1.5/Crânio81_1 \
  resultados/historico/rascunho_sensibilidade_1.2/Crânio81_1 \
  resultados/historico/revisao_automatica/Crânio81_1
```

Resultados obtidos nesta execução:

| Imagem | Regiões base | Estáveis sem alerta | Na fila de revisão | Novos IDs em 1,2 |
|---|---:|---:|---:|---|
| Crânio81_1 | 24 | 22 | 2 | — |
| Crânio81_2 | 23 | 22 | 1 | A9 |
| Crânio81_4 | 24 | 22 | 2 | — |
| Mão46_1 | 25 | 20 | 5 | A5, A21 |
| Mão46_2 | 24 | 21 | 3 | — |
| Mão46_4 | 23 | 22 | 1 | A9 |
| Tórax125_1 | 24 | 22 | 2 | — |
| Tórax125_2 | 5 | 0 | 5 | A4 |
| Tórax125_4 | 1 | 0 | 1 | — |

Esses números mostram apenas concordância entre duas configurações do mesmo
algoritmo. Em particular, Tórax125_2/4 permanecem sem máscara de referência
confiável. Não passar `rascunho_automatico.npz` a `main.py --referencia` para
publicar precisão, revocação ou Dice: isso compararia o detector consigo
mesmo. A confirmação independente pode ser feita revisando e corrigindo as
pré-máscaras no ImageJ, em vez de desenhar todas as ROIs do zero.

Após revisar o TIFF dos rótulos, exporte-o sem reescalonar e converta:

```bash
venv/bin/python -m segmentador_fantomas.converter_referencia referencias/cranio81_1_revisado.tif \
  referencias/cranio81_1_revisado.npz
```

Cada objeto deve preservar um rótulo inteiro distinto; marque falsos positivos
com zero e acrescente regiões extras apenas quando sustentadas pela imagem.
Só depois use esse NPZ revisado em `main.py --referencia`.
