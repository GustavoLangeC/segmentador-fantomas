# Tarefa para anotação independente dos DICOMs

**Destinatário:** pessoa que fará a anotação manual e pessoa que a conferirá.
**Objetivo:** produzir referências independentes para medir a acurácia do
detector. O pesquisador pode entregar este documento junto aos DICOMs por um
canal autorizado; os arquivos originais não devem ser publicados no GitHub.

## Instrução curta para encaminhar ao anotador

> Delineie, em cada DICOM, todas as perfurações que conseguir reconhecer pela
> imagem. Faça isso sem ver as máscaras, contagens ou rankings do programa.
> Use um rótulo inteiro positivo diferente para cada região e zero para o
> fundo. Registre regiões ambíguas em uma lista separada, sem completar uma
> quantidade esperada. Salve os rótulos no tamanho total da imagem e informe
> quais critérios visuais usou. Não atribua profundidade pelo brilho.

## Arquivos e ordem sugerida

Primeira rodada: `Crânio81_1`, `Mão46_1`, `Tórax125_2` e `Tórax125_4`.
Depois, os demais cinco DICOMs: `Crânio81_2`, `Crânio81_4`, `Mão46_2`,
`Mão46_4`, `Tórax125_1`. A ordem prioriza um caso de cada técnica e dois casos
que o programa hoje declara inconclusivos; **não** comunica ao anotador os
contornos automáticos nem uma contagem-alvo.

Para reduzir viés, o anotador A trabalha sozinho a partir dos DICOMs originais.
Um revisor B verifica pelo menos as imagens da primeira rodada sem editar a
versão A silenciosamente. Discordâncias são registradas por região e resolvidas
em uma versão de consenso. O mesmo procedimento pode ser estendido às nove
imagens se houver tempo.

## Como anotar no programa

Na pasta `segmentador-fantomas`, com os DICOMs em `dicom/`:

```bash
venv/bin/python -m segmentador_fantomas.anotar_referencia \
  dicom/Crânio81_1 referencias/anotador_A/Crânio81_1
```

A janela abre a imagem inteira com todos os rótulos zerados. **Novo objeto**
cria um ID; arrastar com o botão esquerdo pinta, `Shift` com arrasto apaga,
`Z` desfaz, `[` e `]` mudam o pincel, e `S` salva. Salvar cria
`referencia_manual_NNN.npz` e um JSON homônimo com SHA-256 do DICOM, data e
origem. Cada salvamento é uma versão; não sobrescreva a anterior. O contraste
da tela é ajustado só para visualização; a máscara usa coordenadas dos pixels
originais. Se preferir ImageJ/Fiji, exporte uma máscara TIFF ou NPY de rótulos
com o mesmo tamanho do DICOM e converta usando
`segmentador_fantomas.converter_referencia` conforme
[`AVALIACAO_SEGMENTACAO.md`](AVALIACAO_SEGMENTACAO.md).

## Critérios de anotação e registro

- Desenhe a área visualmente atribuível à perfuração. Não use círculo ou
  diâmetro presumido para preencher uma borda invisível.
- Não junte duas regiões distintas no mesmo ID. Não divida uma região
  contínua em vários IDs apenas por variação interna de intensidade.
- Se o limite estiver ambíguo, registre ID, coordenadas aproximadas,
  incerteza e motivo em `observacoes.csv`. Não invente um contorno preciso.
- Registre se houve inversão de escala ou alteração de janela **somente na
  exibição**. Não altere o DICOM nem normalize seus pixels para a referência.
- Não use ordem por intensidade, rank, grade ou quantidade esperada para
  identificar a profundidade. O mapa físico é outra tarefa e exige fonte
  documental do fantoma.

Modelo de `observacoes.csv`:

```csv
dicom,rotulo,estado,justificativa,anotador,revisor
Crânio81_1,1,visivel,borda_parcialmente_difusa,A,
Crânio81_1,2,incerto,contraste_insuficiente,A,
```

## Entrega e conferência técnica

Entregar para cada DICOM: arquivo NPZ de `labels`, JSON de proveniência,
`observacoes.csv` e, se houver, versão do revisor B. O array `labels` deve
ser 2D, inteiro e ter exatamente as dimensões do DICOM; `0` é fundo e cada
região usa um inteiro positivo exclusivo. Não inclua os DICOMs no repositório
público do código.

Confira o formato e o vínculo com o arquivo original antes de calcular
métricas:

```bash
venv/bin/python -m segmentador_fantomas.validar_referencia \
  dicom/Crânio81_1 \
  referencias/anotador_A/Crânio81_1/referencia_manual_001.npz \
  --saida referencias/anotador_A/Crânio81_1/conferencia_001.json
```

O validador confere dimensões, tipo de rótulo, SHA-256 quando disponível,
área, centroide e número de componentes por ID. **Passar nessa checagem não
comprova que o contorno está correto.** O revisor B deve inspecionar a imagem
e registrar concordância e divergências. Depois da conferência humana, rode
o detector em uma saída nova com `--referencia`:

```bash
venv/bin/python main.py Crânio81_1 --sem-grafico \
  --output-dir resultados/avaliacao_anon_A_Cranio81_1 \
  --referencia referencias/anotador_A/Crânio81_1/referencia_manual_001.npz \
  --iou-minimo 0.5
```

`avaliacao_referencia.json` conterá TP, FP, FN, precisão, revocação, F1,
IoU/Dice de primeiro plano e erro de centroide. Relate separadamente os casos
ambíguos e as diferenças entre anotadores. Nunca use uma máscara automática
revisada como referência independente do mesmo detector.

## Critério de aceite da tarefa

Cada imagem entregue precisa de NPZ legível, SHA-256 do DICOM documentado,
lista de regiões incertas e revisão humana registrada. A meta é uma referência
auditável; não há exigência de produzir 24 ou 25 regiões. A análise científica
de FP/FN só começa depois desse aceite.
