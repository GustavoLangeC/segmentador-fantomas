# Profundidades informadas na interface

**Data:** 16 de novembro de 2026.

## Fluxo para reconstruir curvas por profundidade

1. Abra `venv/bin/python interface.py` ou `Radio2.desktop`.
2. Clique em **Abrir lote existente** e escolha
   `resultados/lote_demonstracao_2026-11-16` (ou processe um lote novo).
3. Selecione um DICOM e clique em **Revisar máscara e profundidade**.
4. Na janela de revisão, escolha o objeto diretamente na imagem com o botão
   direito ou na lista lateral. Para o objeto selecionado, escolha `inserto`,
   `artefato`, `incerto` ou `não avaliado`. Se escolher `inserto`, digite sua
   profundidade em milímetros. Se digitar a profundidade primeiro, a classe
   muda automaticamente de `não avaliado` para `inserto`. Pode usar vírgula decimal. Não use o rank de
   sinal como prova de profundidade e não preencha uma região apenas para
   completar a contagem esperada.
5. Clique em **Salvar e recalcular**. A pasta `revisoes/revisao_NNN` recebe
   a máscara e o CSV recalculado. Se houver classificação, observação ou
   associação física anterior, recebe também `mapa_profundidades.json` e uma
   versão `mapa_profundidades_NNN.json`. Havendo ao menos um inserto mapeado,
   recebe `curvas_profundidade.png` e `curvas_profundidade.html`.
6. Se o lote contiver outras exposições da mesma técnica, o programa tenta
   preencher automaticamente seus mapas por proximidade exclusiva dos
   centroides. Por exemplo, após mapear Mão 1, ele tenta Mão 2 e 4. O aviso
   ao salvar informa quantas regiões foram preenchidas; `transferencia_grupo.json`
   na revisão de origem detalha os pares, distâncias e omissões.
7. Confira os mapas transferidos abrindo Mão 2/4 ou Crânio 2/4 em **Revisar
   máscara e profundidade**. Regiões sem correspondência ficam `não avaliado`;
   imagens inconclusivas não recebem transferência. Um mapa editado pelo
   usuário no alvo não é sobrescrito. Clique em **Gerar curvas do lote** após
   a conferência. O HTML e as figuras vão para `curvas_fisicas/` dentro do lote.

O editor aceita um mapa parcial: os rótulos que não souber identificar podem
ficar como `não avaliado` ou `incerto`. Ao salvar, as associações acompanham
os rótulos editados mesmo que os IDs do CSV sejam renumerados. O gerador do
lote usa a revisão mais recente de cada imagem; uma revisão sem mapa é omitida.
Mapas transferidos trazem `origem=transferencia_espacial_automatica` e
`proveniencia_transferencia` com distâncias e SHA-256 da origem. São
sugestões espaciais, pendentes de conferência; não provam que a perfuração
física foi identificada corretamente. A associação ocorre depois da detecção
e não pressupõe grade, quantidade ou formato dos insertos.

Pelo terminal, a janela de mapeamento separada continua disponível. Se existir
uma revisão, informe a pasta da revisão mais recente; o gerador do lote usa
essa versão das medições. Para um lote sem revisões:

```bash
venv/bin/python -m radio2.mapear_profundidades \
  resultados/lote_demonstracao_2026-11-16/001_Crânio81_1
venv/bin/python -m radio2.gerar_curvas_fisicas_lote \
  --lote resultados/lote_demonstracao_2026-11-16
```

Se o mapa da imagem de origem já tiver sido salvo pelo terminal, a transferência
para as exposições do mesmo lote pode ser executada com:

```bash
venv/bin/python -m radio2.transferir_profundidades \
  resultados/lote_demonstracao_2026-11-16/001_Crânio81_1
```

Se a origem tiver uma revisão, use o caminho da revisão mais recente no lugar
da pasta do resultado automático. A interface executa essa transferência ao
salvar o mapa da origem; o comando acima serve para repetir a operação.

O mapa é **identificação física informada pelo usuário**, salva depois da
detecção. O SHA-256 de `resultados.csv` impede reutilizar silenciosamente um
mapa com outra versão das medições. O usuário pode deixar regiões sem classe
ou profundidade quando houver incerteza. O JSON registra as coordenadas e a
classe de cada ID; `artefato` e `incerto` não entram nas curvas físicas.
As séries comparativas usam apenas insertos sem alerta heurístico. Imagens
com análise inconclusiva não entram em comparações quantitativas. A
normalização entre kVp é dividida pelo máximo da própria série nas
profundidades comuns, adaptação explicitada no relatório.

## O que ainda precisa de validação

O TCC menciona 24 ROIs, profundidades de 0 a 24 mm e exclusão do furo
passante; essa correspondência não está inequívoca no texto. A interface
não atribui profundidade por grade, rank ou número de regiões. O mapa
informado ainda deve ser conferido com documentação física do fantoma.
Além disso, informar profundidades não valida o contorno das máscaras;
FP, FN, Dice/IoU e erro de centroide exigem referências manuais
independentes, obtidas no modo **Anotar referência**.

## Verificações de implementação

- Sem mapas reais, o gerador de curvas físicas produziu zero figuras e
  listou as nove omissões. Nenhuma curva física foi fabricada.
- Com nove mapas **sintéticos em `/tmp`** (profundidade artificial igual ao
  índice de cada linha, apenas para testar o software), produziu 16 figuras
  análogas às Figuras 19–34 e tabelas HTML. Excluiu Tórax125_2/4 pelo estado
  inconclusivo. As figuras sintéticas não são resultados científicos.
- Sete testes sintéticos passaram, incluindo versionamento do mapa,
  validação de entradas e recusa de mapa associado a outro CSV.
- O gerador lê as medidas exportadas e não reexecuta nem modifica o detector.
  A interface gráfica não pôde ser testada visualmente neste ambiente.
