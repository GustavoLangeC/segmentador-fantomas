# Plano de continuidade — IC de análise de fantomas radiográficos

**Versão inicial:** 16 de novembro de 2026.

## Objetivo geral

Desenvolver e avaliar um método genérico para segmentar insertos visíveis em
radiografias DICOM de fantomas, medindo sinal e incerteza sem usar número,
forma, raio, grade ou posição previamente conhecidos. A identificação física
das perfurações, quando disponível, será uma etapa de validação externa e não
uma condição do detector.

## Objetivos específicos

1. Organizar os nove DICOMs e seus metadados de aquisição em uma tabela
   reproduzível, preservando os pixels originais para todas as medições.
2. Produzir referências manuais independentes para avaliar a segmentação,
   inicialmente em imagens representativas e depois em todo o conjunto que
   tiver contraste suficiente.
3. Medir o desempenho do detector atual por objeto: TP, FP, FN, precisão,
   revocação, F1, Dice/IoU e erro de centroide.
4. Corrigir FP, fragmentações e grandes regiões espúrias com evidência das
   métricas, mantendo a detecção livre de geometria pré-imposta.
5. Comparar sinal bruto, fundo local e sinal corrigido, sem tratar o ranking
   de intensidade como profundidade física comprovada.
6. Usar XRMC como experimento físico complementar para testar hipóteses de
   transmissão, não para fornecer a geometria ao segmentador.
7. Consolidar código, dados de referência, comandos, resultados e limitações
   para relatório científico e possível publicação.

## Fases, entregas e critérios de passagem

| Fase | Entrega verificável | Meta / critério de passagem |
|---|---|---|
| 1. Linha de base | Execução dos 9 DICOMs, CSV/JSON/máscaras e tabela de ambiente/parâmetros | Cada execução deve ser reproduzível por comando registrado; contagem isolada não será aceita como métrica de acurácia. |
| 2. Verdade de referência | Máscaras manuais por instância e protocolo de anotação | Revisar visualmente as anotações; registrar imagens em que não há contraste suficiente em vez de inventar rótulos. |
| 3. Avaliação | Relatório por imagem com TP, FP, FN, precisão, revocação, F1, Dice/IoU e erro de centroide | Estabelecer a linha de base quantitativa antes de qualquer alteração do detector. |
| 4. Melhorias do detector | Mudanças pequenas, comparação antes/depois e testes sintéticos | Aceitar uma mudança somente se não piorar as métricas agregadas e se seus ganhos/perdas por imagem forem reportados. Não usar grade, Hough ou formato esperado como requisito. |
| 5. Medidas radiométricas | Tabela de sinal bruto, fundo, sinal corrigido, RSR, RCR e alertas de qualidade | Demonstrar, por referência externa, se uma correção melhora ou não a repetibilidade/ordenação; manter as três grandezas separadas. |
| 6. Simulação XRMC | Casos versionados com manifesto, NPY, PNG e teste físico | Começar por transmissão primária; acrescentar espectro, ruído e espalhamento apenas com parâmetros documentados e comparação experimental. |
| 7. Consolidação | Relatório técnico, figuras, limitações e repositório reexecutável | Toda afirmação de desempenho deve apontar para dados, máscaras de referência e comando reproduzível. |

## Metas de curto prazo (próximas 4–6 semanas)

1. Criar a planilha/tabela de metadados dos nove DICOMs e salvar uma linha de
   base com `--output-dir` para cada arquivo.
2. Anotar manualmente, no mínimo, `Crânio81_1`, `Mão46_1` e `Tórax125_2`.
   As duas primeiras representam casos utilizáveis; Tórax125_2 testa a recusa
   de componentes grandes e pouco confiáveis.
3. Rodar `--referencia` e publicar a primeira tabela de métricas por imagem.
4. Priorizar dois defeitos mensuráveis: fragmentos/falsos positivos em
   `Mão46_1` e aceitação indevida em `Tórax125_2/4`.
5. Reexecutar o caso XRMC mínimo e registrar a razão furo/PMMA; preservar a
   imagem PNG somente como prévia, com NPY como dado numérico de origem.

## Metas de médio prazo (2–4 meses)

1. Cobrir todos os DICOMs interpretáveis por referência manual e classificar
   explicitamente os casos sem contraste confiável.
2. Avaliar robustez entre 1, 2 e 4 mAs e entre as técnicas de Crânio, Mão e
   Tórax, sempre separando falha segura de falsa detecção.
3. Executar um estudo controlado das correções de fundo: razão local atual,
   alternativa 2D robusta e, se viável, protocolo inspirado na ROI de
   referência do TCC. Nenhuma será declarada superior sem métrica externa.
4. Expandir o XRMC em passos independentes: espectro polienergético
   documentado, ruído de contagem e espalhamento; comparar perfis relativos
   com medidas experimentais antes de reivindicar realismo quantitativo.

## Indicadores que serão acompanhados

- Segmentação: TP, FP, FN, precisão, revocação, F1, Dice, IoU e erro de
  centroide por inserto.
- Medição: diferença de sinal da ROI, fundo local, DP, RSR, RCR e
  repetibilidade entre exposições.
- Robustez: resultado por técnica/mAs, taxa de recusa segura e tempo/memória.
- Simulação: razão de transmissão furo/PMMA, perfil espacial e concordância
  relativa com medições experimentais quando existirem.

## Limites metodológicos

O conjunto conhecido de furos pode ser usado somente na avaliação externa. A
simulação XRMC atual (50 keV monoenergético, sem espalhamento) é um controle
de sanidade física, não um modelo do Philips DigitalDiagnost C50. Um rank por
sinal bruto ou corrigido não identifica a profundidade física. Esses limites
devem constar em toda figura, tabela ou conclusão que use os resultados.
