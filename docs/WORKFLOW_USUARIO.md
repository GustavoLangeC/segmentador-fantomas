# Fluxo de uso: lote, revisão e exportação

**Versão inicial:** 16 de novembro de 2026.

## Para quem não usa terminal

Na pasta do projeto, execute `venv/bin/python instalar_atalho.py` uma vez.
Depois abra **Segmentador de Fantomas** no menu de aplicativos. A janela
também pode ser iniciada com `venv/bin/python interface.py`. Ela permite escolher arquivos DICOM
individuais ou uma pasta, configurar a sensibilidade (padrão 1,5), escolher
uma pasta de saída e iniciar o lote. A lista mostra sucesso ou falha por
arquivo. Selecione um resultado e clique em **Revisar máscara e profundidade**.
Na seção **Simulação e avaliação**, escolha um cenário XRMC ou analítico e
clique em **Simular e avaliar**; o HTML abre quando a análise termina.

O resumo separa `status=concluido` (programa terminou) de
`qualidade_analise=provisoria` ou `inconclusiva` (interpretação dos candidatos).
Um resultado inconclusivo continua disponível para revisão, mas não deve ser
tratado como medição validada.

Para criar uma referência independente, selecione um DICOM e clique em
**Anotar referência**. Esse modo abre a imagem inteira com rótulos vazios,
sem mostrar as máscaras do detector. Pinte um objeto por rótulo, crie novos
rótulos com `N` e salve versões com `S`. Os NPZs e seus JSONs de proveniência
ficam em `referencias/<nome-do-DICOM>/` e precisam de conferência humana.

Para curvas por profundidade, abra um lote existente (ou processe um novo),
selecione uma imagem e clique em **Revisar máscara e profundidade**. Na mesma
janela, selecione um rótulo pelo botão direito na imagem ou pela lista lateral,
marque sua classe e digite a profundidade física em milímetros quando souber.
O botão **Salvar e recalcular** grava uma revisão da máscara, o mapa associado
ao CSV dessa revisão e as curvas individuais quando houver insertos mapeados.
Quando as outras exposições da mesma técnica já estão no lote, o programa
reaproveita automaticamente as classes e profundidades nas regiões que têm
correspondência espacial exclusiva. Assim, mapear Mão 1 pode preencher Mão 2
e 4; mapear Crânio 1 pode preencher Crânio 2 e 4. Objetos sem par ficam sem
associação e imagens inconclusivas são omitidas. Abra os alvos para conferir
as sugestões; correções manuais neles não são sobrescritas por nova
transferência. Depois, clique em **Gerar curvas do lote**. O procedimento detalhado está em
`docs/MAPEAMENTO_PROFUNDIDADES.md`.

Cada DICOM processado agora gera automaticamente um relatório HTML individual
com quatro gráficos (sinal bruto, sinal corrigido, RSR e RCR) e uma tabela de
medições. No lote, o arquivo fica dentro da pasta de cada imagem como
`relatorio_<nome>.html`; selecione o resultado na janela e clique em
**Abrir relatório**. Ao salvar uma revisão, a pasta `revisao_NNN` recebe
`relatorio_revisado.html` com as medidas recalculadas. Esses gráficos usam IDs
espaciais, não profundidades físicas.

No editor, clique com o botão direito em um objeto para selecioná-lo. O botão
esquerdo pinta pixels com seu rótulo; `Shift` + botão esquerdo apaga pixels.
Os números dos rótulos aparecem diretamente sobre a imagem; a lista lateral
permite selecionar e localizar cada objeto. Classe e profundidade ficam ao
lado da imagem. O mapa físico é informado pelo usuário e não entra na detecção.
`N` cria um novo rótulo, `Z` desfaz, `[` e `]` ajustam o pincel, e os botões
alteram o zoom. `S` salva uma versão e recalcula todas as medidas. O pincel
redondo é apenas uma ferramenta de edição livre: não impõe circularidade à
detecção nem ao objeto final. Cada salvamento cria uma versão numerada em
`revisoes/`, preservando a saída automática e revisões anteriores.

## Terminal e automações

O comando original continua válido:

```bash
venv/bin/python main.py Mão46_1 --sem-janela --output-dir resultados/ma_detecao
```

Para abrir a anotação manual em branco pelo terminal:

```bash
venv/bin/python -m segmentador_fantomas.anotar_referencia dicom/Crânio81_1 referencias/Crânio81_1
```

Esse comando também grava `resultados/ma_detecao/relatorio_Mão46_1.html`.
Sem `--output-dir`, o HTML fica no diretório de execução. `--sem-grafico`
continua significando somente resultados numéricos e não cria o relatório.
As comparações entre mAs e kVp do TCC dependem de várias imagens e são
geradas separadamente por `gerar_resultados_tcc.py` quando há o lote completo.

Para processar uma pasta inteira, inclusive DICOMs sem extensão:

```bash
venv/bin/python -m segmentador_fantomas.processar_lote --dicom-dir dicom \
  --output-dir resultados/lote_exemplo --sensibilidade 1.5
```

Ou selecione arquivos específicos:

```bash
venv/bin/python -m segmentador_fantomas.processar_lote dicom/Crânio81_1 dicom/Mão46_1 \
  --output-dir resultados/lote_dois --sensibilidade 1.5
```

O lote roda um DICOM por processo, sequencialmente, e continua depois de
falhas isoladas. Cada arquivo ganha pasta numerada, `resultados.csv/json`,
`mascaras.npz`, PNG e `execucao.log`. `resumo_lote.csv/json` registra status,
contagem, quantidade de regiões com alerta e duração por arquivo. O status
`concluido` significa que o processamento terminou sem erro de software; as
regiões com alerta precisam de revisão. Para evitar sobrescrita, a saída CLI deve ser
uma pasta nova ou vazia. A janela cria um nome novo quando a pasta escolhida
já contém dados.

Para editar um resultado individual por janela:

```bash
venv/bin/python -m segmentador_fantomas.editor_mascaras dicom/Mão46_1 resultados/ma_detecao \
  resultados/ma_detecao/revisoes
```

Para recalcular uma máscara editada por outro programa, grave NPZ com
`labels` e `crop_bbox_yxwh` iguais ao recorte original e execute:

```bash
venv/bin/python -m segmentador_fantomas.quantificar_mascaras dicom/Mão46_1 resultados/ma_detecao \
  caminho/mascara_editada.npz resultados/ma_revisada
```

Na revisão, a média e o desvio padrão são novamente calculados nos pixels
brutos do DICOM, o fundo local é estimado em torno da máscara editada e o
sinal corrigido experimental é atualizado. `alteracoes.json` mostra quantos
pixels foram adicionados/removidos. IDs espaciais e ranks podem mudar após
adicionar ou remover objetos; `rotulos_origem` registra o vínculo entre os
novos IDs e a máscara editada. A revisão humana deve ser identificada como
tal; uma máscara automática sem conferência não vira referência independente.
As curvas do lote usam o CSV e o mapa da revisão mais recente de cada imagem.
Se a revisão mais recente não tiver mapa, a imagem é omitida das curvas até
que a associação seja conferida nessa versão.
Mapas transferidos são identificados como pendentes de conferência visual no
JSON, nos gráficos e na janela de revisão. A transferência usa posições dos
objetos já detectados; não altera a detecção.

## Decisão de desempenho

Para lotes de dezenas de imagens, manter Python com NumPy, SciPy e OpenCV é
adequado como primeira escolha: as operações mais custosas já executam em
bibliotecas compiladas. O lote sequencial evita manter 20 imagens DICOM na
memória ao mesmo tempo. A otimização seguinte deve medir tempo e pico de RAM
por etapa, especialmente filtros gaussianos e refinamento local. Só vale
considerar C++ depois de demonstrar um gargalo concreto que não se resolva
com menos cópias, recortes locais ou processamento em processos separados.

## Limitações verificadas

A janela usa Tkinter e requer uma sessão gráfica. Neste ambiente de execução
sem tela, foram testados os scripts CLI, o lote e o recálculo de uma edição
programática; a interação com mouse e teclado ainda precisa de um teste
visual no computador do usuário. As imagens de Tórax com baixo contraste
continuam exigindo avaliação de qualidade, mesmo quando o lote conclui sem
erro de software.

## Verificação desta versão

Foram executados:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m segmentador_fantomas.processar_lote --dicom-dir dicom \
  --output-dir resultados/lote_demonstracao_2026-11-16 --sensibilidade 1.5
```

Os quatro testes sintéticos passaram. Os nove DICOMs terminaram com status
de execução concluída; o tempo somado foi 50,51 s (de 5,08 a 5,98 s por
arquivo). As contagens foram Crânio 24/23/24, Mão 24/24/23 e Tórax 24/5/1.
Esse lote foi criado antes da inclusão da coluna `regioes_com_alerta` no
resumo; um teste posterior com `Mão46_1` registrou quatro regiões com alerta.
Um arquivo não DICOM foi informado junto com `Mão46_1`: o lote registrou a
falha do primeiro, continuou e concluiu o segundo.

Ao recalcular a máscara automática de `Mão46_1` sem edição, as 24 áreas e
medidas numéricas permaneceram exatamente iguais. Em uma cópia de teste,
foram apagados 1763 pixels de R009: sua área mudou de 3593 para 1830 px e
seu sinal bruto de 2829,80 para 2780,97. A saída automática foi preservada.
Isso verifica propagação da edição às medidas, não a correção física desse
recorte artificial.
