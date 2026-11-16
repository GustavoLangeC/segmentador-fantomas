# Instruções para Codex — IC de análise de fantomas radiográficos

## Comece por aqui
1. Leia `CONTEXTO_IC.md` integralmente antes de propor ou modificar a implementação.
2. Inspecione o `main.py` **real deste repositório** e os DICOMs disponíveis em `dicom/`. O código atual é a fonte da verdade sobre a implementação; o documento histórico descreve intenções, testes e limitações, não substitui sua inspeção.
3. Responda em português brasileiro, com clareza técnica e sem afirmar que algo foi validado sem testes reproduzíveis.

## Objetivo que não pode ser descaracterizado
Desenvolver um segmentador **genérico** de insertos em imagens DICOM de fantomas radiográficos, sem fornecer previamente o número, o formato, o raio, o tamanho, a distribuição espacial ou a grade dos insertos. A detecção deve usar evidências da imagem (contraste local, máscaras, componentes conectados). Não introduza Hough/grade 5×5, posições fixas ou suposição de círculos como requisito da detecção. Os fantomas conhecidos podem ser usados **somente como dados de validação externa**, mediante distinção explícita entre detecção e identificação física.

## Restrições fundamentais
- Preserve os valores originais de `pixel_array` para medições. Suavização e normalização só para localizar/segmentar; não substituir silenciosamente sinal bruto por sinal processado.
- Preserve separadamente: `sinal_bruto`, `fundo_local`, `sinal_corrigido`, métricas de ruído, área, centroide e máscara. A correção vigente é uma **adaptação experimental**, não prova de eliminação do efeito anódico.
- Nunca trate a ordem por intensidade (mesmo corrigida) como identificação comprovada da profundidade física. O ranking pode inverter e deve ser reportado como tal.
- Não forçar o algoritmo a devolver 25 ou 24 objetos. Registrar falsas detecções, falhas e incerteza; em imagens sem contraste suficiente, falhar de modo seguro e transparente.
- Preservar o algoritmo de recorte externo que já funcionou, a menos que exista evidência reproduzível de regressão ou exigência nova. Este recorte externo usa uma região aproximadamente retangular; a liberdade de formato exigida é a dos **insertos**.
- Evitar regressões e consumo excessivo de RAM. Houve encerramento do processo com `Morto`; a versão otimizada usou ~200 MB em testes anteriores. Cuidado com matrizes 2D gigantes, múltiplas cópias float64 e regressões polinomiais com todas as amostras simultaneamente.
- Não mudar interface CLI existente sem necessidade. Comando principal: `python3 main.py Crânio81_1` (arquivo em `dicom/`). Opções já usadas: `--sensibilidade`, `--min-area`, `--sem-janela`, `--sem-grafico`, `--matplotlib`; confirme quais existem na versão local.
- O usuário valoriza mudanças implementadas e testadas, não promessas, explicações longas sem código ou resultados inventados. Ao entregar mudanças, mostrar os comandos exatos, o que foi medido, em quais arquivos e o que permanece não validado. Quando pedir o arquivo completo no chat, fornecer o `main.py` inteiro.

## Fluxo de trabalho
- Antes de cada alteração: verificar `git status`, fazer um plano breve e identificar uma métrica de sucesso.
- Rodar comparação **antes/depois** nos DICOMs existentes; não usar apenas a contagem de objetos como prova de acurácia.
- Preferir melhorias localizadas e reversíveis; manter sinais brutos e corrigidos lado a lado.
- Se código/testes mudarem descobertas relevantes, atualizar `CONTEXTO_IC.md` (data, comando, imagem, sensibilidade, contagem, falsos positivos/negativos, memória, observação). Não sobrescrever históricos confirmados.
- Se houver TCC/PDF local, consulte-o antes de atribuir causa física a efeitos observados.
