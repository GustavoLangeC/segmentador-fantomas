# Figuras e tabelas derivadas dos lotes

**Data:** 16 de novembro de 2026.  
**Fonte metodológica:** `docs/referencias/William da Veiga - TCC 2 - final_banca.pdf`,
seções 3 e 4, especialmente Figuras 15–34 e Equações 1–3.

## Gerar novamente

```bash
cd ~/projects/radio2
venv/bin/python -m radio2.gerar_resultados_tcc \
  --lote resultados/lote_demonstracao_2026-11-16 \
  --revisao-cranio resultados/lote/001_Crânio81_1/revisoes/revisao_002 \
  --dicom-dir dicom \
  --saida resultados/recriacao_tcc_2026-11-16
```

Abra `resultados/recriacao_tcc_2026-11-16/index.html`. O relatório contém
20 figuras novas, numeradas como análogas às Figuras 15–34 do TCC, resumo do
lote e tabelas de todas as 172 regiões exportadas. Cada tabela possui link para
seu CSV de origem. `manifesto.json` registra as fontes usadas.

Para uma imagem DICOM isolada, `main.py` gera automaticamente um relatório
individual HTML com quatro gráficos e tabela sempre que os gráficos estiverem
habilitados. Isso inclui execuções da interface em lote. O relatório comparativo
desta página continua exigindo as várias exposições necessárias.

Foram usados os nove DICOMs do lote completo em sensibilidade 1,5. Para
`Crânio81_1`, a tabela e a máscara vieram da revisão `revisao_002` do lote
posterior. A revisão alterou 694 pixels em relação à máscara automática,
mantendo 24 regiões. Isso registra uma edição, não uma validação independente.
As contagens das nove imagens foram, na ordem Mão 1/2/4, Crânio 1/2/4 e
Tórax 1/2/4 mAs: 24/24/23, 24/23/24 e 24/5/1. Não há referências manuais
para calcular falsos positivos ou negativos. Pico de memória não foi medido.

## Diferenças em relação ao TCC

- A abscissa é o ID espacial da região ou o ID da imagem de referência,
  **não a profundidade física**. A ordem do sinal não comprova profundidade.
- O TCC usou ROIs manuais, fundo acima/abaixo e o fundo da ROI central 12.
  O programa usa núcleo da máscara segmentada, anel de fundo e mediana dos
  fundos válidos. O sinal corrigido é uma adaptação experimental.
- Nas comparações entre imagens, a associação é provisória por centroide
  absoluto em até 35 px, um candidato por posição. Regiões com alerta
  heurístico são omitidas dessas comparações; aparecem marcadas nas figuras
  individuais e permanecem nas tabelas.
- Nas Figuras 27–28 análogas, a normalização foi explicitamente definida como
  sinal corrigido dividido pelo máximo da própria série nas posições comuns.
  O texto do TCC não fornece a operação exata de normalização.
- Tórax125_2 e Tórax125_4 não entraram nas curvas RSR/RCR ou de kVp por
  detecção não confiável. As imagens e as tabelas permanecem no relatório
  para inspeção, com essa restrição visível.
- As Figuras 1–14 do TCC são ilustrações de teoria, equipamento e fantoma;
  não podem ser derivadas dos lotes. Não foram encontradas tabelas numeradas
  na lista de resultados do PDF. As tabelas de medições do relatório são novas.

Para produzir e comparar curvas **por profundidade em milímetros**, falta uma
associação física independente entre cada região segmentada e a perfuração
correspondente, conferida imagem a imagem. A mesma referência deve verificar
FP, FN e erros de contorno. Uma vez disponível, ela pertence à avaliação,
sem entrar como requisito do detector genérico.

## Verificações executadas

O gerador conferiu em cada CSV `RSR = sinal_bruto / desvio_padrao_roi` e
`RCR = |sinal_bruto - fundo_local| / desvio_padrao_fundo`. Depois da geração,
foram verificados 20 arquivos PNG, nove links de CSV e 191 linhas de tabela
HTML (nove resumos, nove cabeçalhos de detalhe e 172 medições, mais o
cabeçalho do resumo). As figuras foram inspecionadas visualmente em folhas de
contato. Isso verifica a exportação e o cálculo, não a acurácia científica.
