# Contexto técnico e histórico da Iniciação Científica (IC)

**Última consolidação:** 15 de novembro de 2026.  
**Idioma de trabalho:** português brasileiro.  
**Ambiente do usuário:** Debian/Linux, Python 3, virtualenv `venv`, projeto atual `~/projects/radio2`, arquivo principal `main.py`, arquivos radiográficos em `dicom/`.  
**Responsabilidade do Codex:** ler o `main.py` atual antes de implementar mudanças; este documento não é uma cópia atualizada do código.

## 1. Finalidade da pesquisa

Automatizar a leitura e a análise de radiografias DICOM de fantomas de acrílico/PMMA, localizando insertos ou perfurações, delineando suas regiões de interesse (ROIs) e extraindo características quantitativas dos pixels (área, centroide, média, desvio padrão, contraste, fundo e sinal corrigido). Eliminar a seleção manual no ImageJ e posteriormente **validar** detecção e medições frente a anotações de referência.

**Decisão explícita mais recente:** O detector de insertos deve ser **genérico e agnóstico à geometria**. Não pode receber grade 5×5, número de furos, raio, circularidade, tamanho ou disposição predefinidos. A geometria conhecida do fantoma experimental é útil como *verdade externa de validação*, NÃO como parâmetro do detector genérico. Houve uma versão anterior específica que usava grade 5×5 e funcionou em Crânio/Mão; o usuário abandonou essa restrição em favor da generalização. Não retomar a grade como solução principal.

## 2. DICOMs de referência

O conjunto tem nove imagens nomeadas de modo a codificar técnica e exposição:

| Técnica | kVp | Arquivos | Observações |
|---|---:|---|---|
| Crânio | 81 | `Crânio81_1`, `Crânio81_2`, `Crânio81_4` | 1, 2, 4 mAs |
| Mão | 46 | `Mão46_1`, `Mão46_2`, `Mão46_4` | 1, 2, 4 mAs |
| Tórax | 125 | `Tórax125_1`, `Tórax125_2`, `Tórax125_4` | 1, 2, 4 mAs; contraste insuficiente/saturação em várias imagens |

Suffixes `_1`, `_2`, `_4` = valores em **mAs**, não 1, 2, 3. Imagens de Crânio da ordem de 1451×1484 px, `uint16`, valores de 0 até 4095 e `MONOCHROME2` nos exemplos. Ler metadados reais em cada arquivo; não presumir constantes para todo o conjunto. A pasta `dicom/` pode conter arquivos sem extensão `.dcm`.

## 3. Referência acadêmica crucial — TCC de William da Veiga (UTFPR, 2026)

Título: *Caracterização de um fantoma para testes de controle de qualidade em radiologia diagnóstica*. O usuário forneceu PDF nesta conversa com ChatGPT, mas **ele pode não estar salvo no repositório local**. Se for necessário comparar metodologia, solicitar cópia do PDF ou localizar o arquivo existente antes de afirmar detalhes adicionais.

Do texto das seções 2.1.1 e 3 (páginas numeradas 14–15 e 27–30):
- Efeito anódico: intensidade do feixe pode variar espacialmente ao longo de uma direção; o trabalho ressalta a importância de considerar isso nas ROIs. Outros fenômenos, como resposta do detector, espalhamento, bordas e pós-processamento, também podem contribuir; não diagnosticar causa física só pela imagem.
- Fantoma descrito como placa de PMMA **25 mm de espessura**, perfurações de **10 mm de diâmetro**, profundidades **0 a 24 mm**; o autor declara ter excluído o furo de 24 mm por ter atravessado a placa. O texto também menciona **24 ROIs** e análise de furos de 1–23 mm. Há **aparente inconsistência** entre essas contagens/dimensões; confirmar com o orientador/documentação antes de associar índices físicos. A interpretação inicial do usuário de '1 a 25 cm' NÃO deve ser usada como dimensão física válida.
- Imagens obtidas com equipamento Philips Digital Diagnost C50; distância foco-detector 1 m; filtro extra 2 mm Al; técnicas Crânio 81 kVp, Mão 46 kVp, Tórax 125 kVp, cada uma com 1, 2 e 4 mAs.
- O TCC usou ImageJ para selecionar ROIs manualmente, medir sinal médio `S`, desvio-padrão, fundo `S_fundo` e calcular RSR/RCR.
- Equação 1 do TCC: `S_corrigido = (S / S_fundo) * S_FC(12)`, onde a referência é o fundo da região central 12. Também relata inversão de escala de cinza para tornar as perfurações mais claras antes de usar seu indicador. Não transpor diretamente o sinal físico/numeração do TCC aos pixels brutos MONOCHROME2 sem documentar convenções.
- Código atual adotou **adaptação**: `S_corrigido = (S_bruto / fundo_local) * mediana(dos fundos locais válidos)`. Isso **não** replica literalmente a ROI 12, e não foi cientificamente validado para remover completamente o efeito anódico.
- Relação sinal/ruído no TCC: `RSR = S_i / sigma_i`; relação contraste/ruído: `RCR = (S_i - S_fundo) / sigma_fundo` (atenção à convenção de sinal e ruído ao comparar com outros protocolos).

## 4. Histórico dos algoritmos e decisões

### Primeira etapa — recorte externo do fantoma
- Algoritmo `PhantomSegmenter` validado visualmente em todos os testes iniciais.
- Percentis 1 e 99 normalizam apenas a imagem de trabalho; Gaussian blur; múltiplos limiares e polaridades; morfologia; contornos; pontuação por dimensão/retangularidade; recuo interno em torno de 1,2% para evitar moldura.
- Crânio81_1 exibiu bbox aprox. `x=181, y=204, w=1127, h=1125`. Preservar esse estágio enquanto funcionar.

### Segunda etapa — detector específico de grade (OBSOLETO para o objetivo atual)
- HoughCircles falhava com furos pouco visíveis, deslocava numeração e usava raios muito pequenos.
- Uso de projeções em X/Y e cinco posições equidistantes em cada eixo resolveu visualmente muitos testes de Crânio/Mão.
- **Esse método não serve ao novo requisito genérico** e não deve ser reintroduzido como pressuposto.
- Ordens físicas anteriormente relatadas: Crânio e Tórax percorrem colunas da direita para esquerda de cima para baixo; Mão colunas esquerda para direita de cima para baixo. Usar só como dado externo se for feita comparação com a placa de teste.

### Terceira etapa — detector genérico (OBJETIVO ATUAL)
- `PhantomSegmenter` recorta exterior; `InsertoDetector` tenta detectar objetos claros e escuros por diferença em relação ao fundo estimado por filtros gaussianos (convolução normalizada dentro da máscara), limiar robusto MAD, histerese, operações morfológicas, rotulagem de componentes conectados.
- As máscaras são refinadas **individualmente** por superfície de fundo local polinomial, ajuste robusto ao redor do candidato, novo contraste e crescimento restrito da região. Esse refinamento corrigiu um recorte parcial no inserto de baixo contraste próximo à direita (chamado região 5 numa versão inicial), de aproximadamente 2,4 mil para aproximadamente 4,4 mil pixels, sem presumir circularidade.
- Métricas por objeto: polaridade, centroide, área px, média e desvio-padrão dos valores brutos do DICOM, amostra central erosionada (para não incluir bordas), fundo mediano em anel ao redor da **máscara real** com exclusão de outros objetos, ruído de fundo, sinal corrigido e contraste relativo.
- `S_ref` = mediana de fundos locais válidos, não ROI 12 física. `contraste_relativo = 100*(S_bruto/S_fundo - 1)`.
- Os objetos são numerados por ordem de **sinal corrigido decrescente**, não por coordenadas. Este número é *rank*, não profundidade comprovada. Um falso positivo pode deslocar todo o ranking.
- Rotina de visualização: imagem de contornos e imagem de máscaras segmentadas com etiquetas. Versão otimizada usa OpenCV para evitar RAM excessiva, salva `resultado_<arquivo>.png`; permite não abrir janela e opcionalmente Matplotlib, conforme versão real.
- Uma versão anterior terminava abruptamente com `Morto` em Debian (suspeita de OOM); otimização reduziu pico registrado de aproximadamente 316 MB para aproximadamente 199 MB. A causa sistêmica do encerramento não foi demonstrada definitivamente.

## 5. Evidências concretas dos testes feitos pelo usuário

Os resultados abaixo não equivalem a validação de verdade-terreno: são contagens e análises visuais de processamento, suscetíveis a falsos positivos, falhas e inversões.

| DICOM | Exemplo de execução | Regiões | Avaliação |
|---|---|---:|---|
| Crânio81_1 | sensibilidade 1.5 ou 1.2 | 24 | Contornos em geral bons; ranking 23/24 invertido fisicamente e inversões locais 3/4, 8/9, 13/14, 18/19 em alguns testes |
| Crânio81_2 | sensibilidade 1.5 | 23 | Inserto de baixo contraste ausente |
| Crânio81_2 | sensibilidade 1.2 | 24 | Reencontrou mais um; conferir falsos positivos |
| Crânio81_4 | sensibilidade 1.2 | 24 | Segmentação visualmente boa; **ranking por sinal corrigido muito embaralhado** nas regiões mais escuras; sensível ao sinal/fundo |
| Mão46_1 | sensibilidade padrão | 25 | Bons contornos em grande parte dos objetos |
| Mão46_1 | sensibilidade 1.2 | 26 | **Dois pequenos fragmentos extras** na borda esquerda de um inserto, falsos positivos; não aumentar sensibilidade cegamente |
| Mão46_2 | sensibilidade 1.2 | 24 | Um ou mais de baixo contraste podem faltar |
| Mão46_4 | sensibilidade 1.2 | 23 | Região(ões) fraca(s) não encontrada(s) |
| Tórax125_1 | padrão/teste visual | ~24 | Contagens não demonstram identificação confiável; imagem com contraste desfavorável |
| Tórax125_2 | exemplos de captura | 5 | Um grande componente é região de fundo, não inserto; **rejeitar como falha** |
| Tórax125_4 | exemplos de captura | 1 | Componente não corresponde a inserto confiável; **rejeitar como falha** |

Exemplo numérico Crânio81_1, classificação corrigida antiga:
- Rank 23 em centro `(120.3,999.5)`: `bruto=1245.06`, `fundo=2200`, `corrigido=1335.32`, `DP=147.73`, área 4836 px.
- Rank 24 em centro `(120.8,779.9)`: `bruto=1192.56`, `fundo=2154`, `corrigido=1306.33`, `DP=131.94`, área 4776 px.
- Diferença corrigida ~28.99 níveis, porém sua relevância física/estatística NÃO foi determinada. Não atribuir esta inversão automaticamente ao furo atravessado, efeito anódico ou grade física.

DICOM Crânio81_4 apresentou grande mudança de ranking entre intensidade bruta e corrigida nas primeiras colunas, sugerindo que a correção atual **não é automaticamente confiável**.

## 6. Problemas atuais e interpretação metodológica

1. **Falsos positivos / divisão de componentes:** fragmentos extras, especialmente Mão46_1 com sensibilidade 1.2; verificar duplicações, máscara de borda, área, conectividade, contraste, solapamento e compactação sem supor formato circular.
2. **Falsos negativos:** regiões de baixo contraste faltando em Crânio81_2 e Mão46_2/4; melhorar sensibilidade local *sem* multiplicar artefatos.
3. **Falsa aceitação de imagem inválida:** Tórax125_2/4 permitem segmentar áreas enormes ou irrelevantes; introduzir controle de qualidade e critérios de rejeição com explicação, sem depender de contagem-alvo conhecida.
4. **Ranking ≠ profundidade física:** correção de sinal ainda não garante ordenação monotônica. Não forçar swaps de posições de ranks, nem chamar rank de profundidade física.
5. **Gradiente de fundo:** a correção por razão de intensidade local e referência mediana pode aliviar gradientes, mas não foi provado que elimina efeito anódico; explorar comparação controlada: bruto vs razão local vs superfície de fundo 2D com ajuste robusto. Comparar contra ground truth e quantificar incerteza.
6. **ROI/medição:** verificar se máscaras capturam área física, quão grande deve ser a erosão interna, dispersão DP, qualidade de fundo (anéis contaminados por bordas), uso de valores originais e efeitos de saturação.
7. **Memória:** otimização para Debian é requisito prático; não criar grandes arrays de design matrix de todas as imagens ou cópias redundantes.

## 7. Plano de pesquisa recomendado (próximos passos)

**Etapa 1 — Validar segmentação antes de mudar correção:**
- Construir anotações de referência no ImageJ (ou ferramenta equivalente) para as regiões visíveis de imagens representativas; preservar máscaras e intensidades manuais.
- Definir regra de associação por sobreposição/distância somente no **módulo de avaliação** (geometria do fantoma não faz parte do detector).
- Medir precisão, revocação, FP, FN, Dice/IoU por ROI, erro de centroide e diferenças de sinal médio. Uma contagem '24' não prova resultado correto.

**Etapa 2 — Qualidade/confiança dos candidatos:**
- Rejeitar segmentos absurdamente grandes, colados à borda, fragmentos duplos, perfis de intensidade sem contraste significativo; considerar critérios com escala relativa robusta e testes de sensibilidade.
- Reportar confiança/alertas de maneira verificável, não inventar scores 'certos' sem calibrá-los.

**Etapa 3 — Estudo de correção de não uniformidade:**
- Preservar simultaneamente sinais brutos, fundo local e corrigido.
- Comparar método inspirado no TCC, modelo 2D robusto e alternativa baseada em diferença ou razão local. Avaliar erros, ruído e ordenação física com verdade de referência.
- Não remover a informação física de interesse ao superajustar um gradiente.

**Etapa 4 — Avaliação da generalização e limites:**
- Testar em diferentes kVp/mAs; caracterizar falha sob contraste insuficiente/saturação.
- Implementar recusa explícita para imagens sem dados confiáveis; nenhuma classificação inventada para Tórax altamente saturado.
- Validar em imagens adicionais com insertos de outras geometrias e disposições se disponíveis, já que a base atual é sempre a mesma placa.

**Etapa 5 — Entrega científica:**
- Dados tabulares/CSV, imagens antes/depois, protocolos reproduzíveis, comparação ImageJ, métricas, limitações e metodologia escrita.

## 8. Instruções operacionais / comandos

No diretório real do projeto (`~/projects/radio2`, não confundir com o primeiro protótipo `~/projects/radio`):

```bash
source venv/bin/activate
python3 main.py Crânio81_1 --sem-janela
python3 main.py Crânio81_2 --sem-janela --sensibilidade 1.2
python3 main.py Mão46_1 --sem-janela --sensibilidade 1.2
```

Outras opções já mencionadas pelo usuário e implementadas em uma versão: `--min-area`, `--sem-grafico`, `--matplotlib`. O programa recebeu inicialmente **um** nome de arquivo por execução; chamada com três nomes foi rejeitada por `argparse`. Não pressupor processamento em lote sem implementá-lo.

Dependências típicas: `pydicom`, `numpy`, `scipy`, `opencv-python`, `matplotlib`; conferir o ambiente com `python3 -m pip list`. Git e teste automatizado são recomendados antes de mudanças grandes.

## 9. Convenções de comunicação com o pesquisador

- O usuário está aprendendo Python, NumPy, matrizes e técnicas de segmentação e quer compreender decisões, embora valorize primeiramente entregas executáveis.
- Não interromper a execução do trabalho para perguntar decisões já respondidas; começar com hipótese/validação explícita.
- Não afirmar “perfeito”, “resolvido”, “validado” sem métrica ou confirmação. Mostrar gráficos comparativos e logs.
- Ao modificar `main.py`, fornecer implementação funcional e testável, indicar o caminho real do arquivo editado, e, se solicitado em conversa, o código completo para copiar.
- Registrar testes com parâmetros exatos em vez de misturar resultados padrão com sensibilidade 1.2.
- Quando detectar contradição entre o TCC, hipóteses iniciais e pixel data, usar documentação científica e validação experimental; não substituir automaticamente uma hipótese por outra.

## 10. Próxima tarefa sugerida para Codex

1. Abrir `main.py` e mapear onde o algoritmo rotula, refina, mescla e classifica regiões e quais recursos usa.
2. Criar relatório antes/depois com referência visual e estatística para os arquivos disponíveis, preferindo **não alterar o detector** na primeira revisão.
3. Corrigir falsas duplicações pequenas e detecção de grandes regiões de fundo sem impor grade/circularidade.
4. Separar números do objeto, rank por bruto, rank por corrigido e identificação física experimental.
5. Planejar com o usuário uma avaliação de referência manual usando ImageJ.

Este documento é um *handoff*: revise-o à medida que surgirem evidências reais. O `main.py`, os DICOMs e logs atuais devem ser usados para confirmar ou corrigir qualquer descrição histórica.

## 11. Atualização — primeira versão avaliável (15 de novembro de 2026)

Foi preservada uma cópia do ponto de partida em
`baseline/main_baseline_2026-11-15.py` (SHA-256
`9678e19e0f3909165a2dc3415726a78ae73506b6465f04b83985478156991c11`).
O detector e a fórmula radiométrica não foram alterados nesta etapa.

### Recursos acrescentados

- `--output-dir` exporta `mascaras.npz`, `resultados.csv`, `coordenadas.csv` e
  `resultados.json`. O NPZ contém rótulos por instância e bbox do recorte.
- `region_id` é um identificador espacial de execução, separado de
  `rank_bruto` e `rank_corrigido`; nenhum é identificação física/profundidade.
- As exportações incluem RSR e RCR. Elas usam sinal bruto, DP da ROI e anel de
  fundo conforme as equações do TCC, sem tornar a correção experimental
  equivalente à ROI 12.
- Alertas heurísticos, sem descarte automático: fundo indisponível, contraste
  local baixo, limites de área e pares possivelmente duplicados/fragmentados.
- `--referencia` compara rótulos manuais por IoU e associação global, exportando
  TP, FP, FN, precisão, revocação, F1, Dice e IoU. A referência não entra na
  detecção.
- `converter_referencia.py` converte máscara manual TIFF/NPY/NPZ; instruções e
  limitações estão em `docs/AVALIACAO_SEGMENTACAO.md`.

### Testes reprodutíveis executados

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python main.py Crânio81_1 --sem-grafico --output-dir /tmp/radio2_export_test
venv/bin/python main.py Crânio81_1 --sem-grafico --output-dir /tmp/radio2_eval_test \
  --referencia /tmp/radio2_export_test/mascaras.npz
```

Passaram três testes sintéticos: detector em retângulo, barra e forma em L; e
avaliação com FP/FN. A segunda comparação usa a própria máscara exportada como
referência e só verifica I/O e métricas, não acurácia científica.

Todos os nove DICOMs disponíveis executaram sem erro com `--sem-grafico` e
`--output-dir`, preservando as contagens baseline para sensibilidade 1,5:
Crânio 24/23/24; Mão 25/24/23; Tórax 24/5/1, em 1/2/4 mAs. Tórax125_2 manteve
cinco regiões suspeitas, incluindo componente de 195007 px perto da área máxima;
Tórax125_4 manteve uma região de contraste local baixo. Isso não autoriza
declarar sucesso nesses casos e reforça a necessidade de referência manual.

## 12. Atualização — experimento físico mínimo XRMC (16 de novembro de 2026)

Foi acrescentado `simulacao_xrmc/`, isolado de `main.py`, para simular uma
aquisição de transmissão e não para fornecer geometria ao detector. O caso
`minimo_pmmaa_furo` contém uma placa de PMMA de 25 mm com uma perfuração
passante de 10 mm, filtro de Al de 2 mm, FDD de 100 cm e detector 256 x 256.
Usa XRMC 6.7.0 e, nesta primeira verificação, fonte monoenergética de 50 keV,
sem espalhamento. Portanto não reproduz nem valida quantitativamente o Philips
DigitalDiagnost C50, as técnicas de 46/81/125 kVp, mAs, ruído ou resposta do
detector do TCC.

Instalação local sem `sudo` e execução:

```bash
./simulacao_xrmc/instalar_xrmc_local.sh
./simulacao_xrmc/executar_minimo.sh
```

No computador atual, a execução levou cerca de 1,3 s de CPU e produziu
`output/image.dat`, `image.npy` e manifesto. A verificação independente da
segmentação mediu transmissão média de 85164,4 no furo e 45958,5 no PMMA
adjacente (razão 1,853070), confirmando somente o sentido físico esperado para
essa geometria conhecida. O conversor também rejeitou deliberadamente uma
dimensão incompatível (`255 x 256`) com `ValueError` de tamanho de arquivo.
Foi corrigida durante a montagem a orientação das normais dos planos e evitada
a coincidência numérica entre as faces da placa e do furo; sem isso o XRMC
simulava vácuo ou anulava o contraste do furo.

### Atualização de visualização (16 de novembro de 2026)

`executar_minimo.sh` passou a gravar também `output/image.png`. É uma prévia
em escala de cinza, limitada aos percentis 1--99 exclusivamente para exibição;
`image.npy` permanece a matriz `float64` sem normalização e é o dado usado em
qualquer análise numérica. O plano de continuidade da IC está em
`docs/PLANO_PESQUISA_IC.md`.

### Atualização — linha de base reexecutada (16 de novembro de 2026)

Foi criada a linha de base em
`resultados/linha_base_2026-11-16_sensibilidade_1.5/`, com CSV, JSON e
máscaras NPZ para os nove DICOMs, executando sensibilidade 1,5. Os três testes
sintéticos passaram. As contagens foram Crânio 24/23/24, Mão 25/24/23 e
Tórax 24/5/1. Isso não constitui acurácia sem referência manual.

Observação visual e por alertas: `Mão46_1` tem o par R005/R010 marcado como
possível fragmentação; `Tórax125_2` contém R002 com 195007 px, próximo da área
máxima, acompanhando fundo amplo na visualização; e `Tórax125_4` contém uma
única região de contraste local baixo. Detalhes, comandos e limitações estão
em `docs/RESULTADOS_LINHA_BASE_2026-11-16.md`.

Também foi adicionado `coletar_metadados_dicom.py`, que lê cabeçalhos com
`stop_before_pixels=True` e não exporta campos de identificação. A execução
gerou `metadados_dicom.csv/json` na linha de base: os nove arquivos são CR,
MONOCHROME2, com 12 bits armazenados em 16 bits, Philips DigitalDiagnost C50,
e registram `Exposure` 1/2/4 conforme o sufixo dos arquivos.

### Atualização — rascunhos automáticos para revisão (16 de novembro de 2026)

`preparar_revisao_mascaras.py` compara os resultados do detector em 1,5 e 1,2
por IoU sem construir uma máscara 2D por par de candidatos. Gerou NPZ de
rascunho, PNG com contornos, fila CSV e resumo JSON para os nove DICOMs em
`resultados/revisao_automatica/`. Os resultados e a interpretação restrita de
estabilidade estão em `docs/REVISAO_MASCARAS_AUTOMATICAS.md`. Essas máscaras
derivam do detector e não são verdade de referência independente; uma
comparação do detector com elas seria circular.

### Atualização — correção de sobreposição em Mão46_1 (16 de novembro de 2026)

Foi observada interseção de 102 pixels entre R005 (421 px) e R010 (3274 px)
em `Mão46_1`, sensibilidade 1,5. Uma mesclagem localizada de fragmentos da
mesma polaridade, baseada na sobreposição real das máscaras e antes das
medições, reduziu 25 para 24 regiões, sem mudar nenhum pixel de primeiro
plano. Os outros oito DICOMs permaneceram idênticos em sensibilidade 1,5.
Quatro testes sintéticos passaram. Em sensibilidade 1,2, `Mão46_1` permaneceu
com 26 regiões; dois candidatos adicionais estão sinalizados para revisão.
Comandos, métricas e limites estão em `docs/CORRECAO_FRAGMENTOS_MAO46_1.md`.

### Atualização — lote e revisão sem Fiji (16 de novembro de 2026)

Foram acrescentados `processar_lote.py` (CLI sequencial com resumo CSV/JSON),
`interface.py` com `Radio2.desktop` (janela Tkinter), `editor_mascaras.py`
(pincel livre, apagar, novo rótulo, desfazer, zoom e salvamentos versionados) e
`quantificar_mascaras.py` (recálculo de sinal bruto, fundo, correção, ruído e
área a partir dos pixels DICOM originais e da máscara revisada). O fluxo está
em `docs/WORKFLOW_USUARIO.md`. O comando principal `main.py` não mudou.

Teste: `venv/bin/python processar_lote.py --dicom-dir dicom --output-dir
resultados/lote_demonstracao_2026-11-16 --sensibilidade 1.5` concluiu os nove
DICOMs em 50,51 s somados, com contagens Crânio 24/23/24, Mão 24/24/23 e
Tórax 24/5/1. Não houve referência manual para TP/FP/FN. Uma edição de teste
em `Mão46_1` removeu 1763 pixels de R009, alterando área 3593→1830 px e
sinal bruto 2829,80→2780,97; a saída automática permaneceu intacta. Recálculo
sem edição reproduziu exatamente as 24 áreas e medidas numéricas. O lote
continuou após um arquivo inválido em teste separado. Interface gráfica não
foi testada com mouse neste ambiente sem display; pico de RAM não foi medido.

### Atualização — figuras e tabelas análogas às do TCC (16 de novembro de 2026)

Foi criado `gerar_resultados_tcc.py`, que lê o lote completo em
`resultados/lote_demonstracao_2026-11-16` e usa, para `Crânio81_1`, a revisão
`resultados/lote/001_Crânio81_1/revisoes/revisao_002`. A execução gerou
`resultados/recriacao_tcc_2026-11-16/index.html`, 20 figuras análogas às
Figuras 15–34 do TCC, tabelas HTML para 172 candidatos e `manifesto.json`.
Comando e limites detalhados: `docs/RECRIACAO_GRAFICOS_TCC.md`.

As nove contagens foram Mão 24/24/23, Crânio 24/23/24 e Tórax 24/5/1,
respectivamente para 1/2/4 mAs, com sensibilidade 1,5. Foram conferidas
as equações de RSR/RCR exportadas e os 20 PNGs e nove links CSV do relatório.
Não há avaliação TP/FP/FN por falta de referência manual; pico de RAM não foi
medido. Tórax125_2/4 foram excluídos das curvas quantitativas por detecção
não confiável. Os gráficos usam IDs espaciais e associação provisória de
centroides entre imagens, nunca profundidades físicas inferidas do ranking.
O sinal corrigido permanece uma adaptação experimental, não a Equação 1
literal do TCC. As Figuras 1–14 do TCC não derivam dos lotes.

### Atualização — relatório individual automático (16 de novembro de 2026)

`main.py` agora cria `relatorio_<DICOM>.html` automaticamente em execuções com
gráficos, ao lado das exportações estruturadas quando há `--output-dir` ou no
diretório de execução caso contrário. O relatório usa SVG leve para quatro
gráficos (bruto, corrigido, RSR e RCR), mais tabela e alertas. Não introduz
hipótese de profundidade física. `--sem-grafico` mantém o comportamento de
somente números. `processar_lote.py` passa a produzir um relatório por imagem
sem mudar sua CLI; a interface oferece botão **Abrir relatório**. Revisões
salvas por `quantificar_mascaras.py` também geram `relatorio_revisado.html`.

Teste reproduzível: `venv/bin/python processar_lote.py --dicom-dir dicom
--output-dir /tmp/radio2_relatorios_auto_2026-11-16 --sensibilidade 1.5`.
Nos nove DICOMs, as contagens permaneceram Crânio 24/23/24, Mão 24/24/23,
Tórax 24/5/1; cada `resultados.csv` foi idêntico linha a linha ao lote anterior.
Os nove HTMLs tinham quatro SVGs e tabelas com contagens correspondentes.
Uma cópia de `Crânio81_1` chamada `imagem_teste.dcm` executou sem
`--output-dir` e gerou `relatorio_imagem_teste.html`. Requantificação da
`mascara_editada_002.npz` preservou as 24 medidas da `revisao_002` e gerou
HTML com quatro gráficos. Quatro testes sintéticos passaram. Em uma execução
de `Crânio81_1 --sem-janela`, VmHWM observado foi 202556 kB e duração 5,35 s;
não constitui medição comparativa formal de pico de RAM. A interface gráfica
atualizada não pôde ser testada com mouse neste ambiente.

### Atualização — limpeza reversível e qualidade da análise (16 de novembro de 2026)

O HTML e PNG soltos na raiz, gerados em execução avulsa de `Crânio81_1`,
foram movidos para `resultados/execucoes_avulsas/Crânio81_1_2026-11-16/`;
hashes SHA-256 permaneceram iguais. DICOMs, ambiente virtual, simulação,
referências, revisões e todos os resultados históricos foram preservados.
Um virtualenv duplicado de 13 MB dentro da saída XRMC foi movido para
`/tmp/radio2_output_venv_backup_2026-11-16`; caches Python foram removidos.
Foram acrescentados `README.md`, `requirements.txt` com versões do ambiente
atual e `resultados/README.md` para orientar execução e proveniência.

`image_quality` agora separa conclusão técnica de interpretação científica.
Sem regiões ou com todos os candidatos alertados, a análise é `inconclusiva`;
com algum candidato sem alerta, `provisoria`, nunca validada. Em nove DICOMs,
sensibilidade 1,5, `resultados.csv`, máscaras NPZ e bboxes foram idênticos à
linha de base `resultados/lote_demonstracao_2026-11-16`. Crânio 24/23/24,
Mão 24/24/23 e Tórax 24/5/1; Tórax125_2 e Tórax125_4 ficaram inconclusivos,
os outros sete provisórios. Os alertas são heurísticos e não substituem FP/FN
contra máscaras manuais. `evaluate_instances` também passou a informar erro
de centroide por associação IoU, testado sinteticamente com deslocamento
de 5 px. Detalhes: `docs/CONTROLE_QUALIDADE_2026-11-16.md`.

Cinco testes sintéticos passaram. Em `Crânio81_1 --sem-janela`, VmHWM foi
202496 kB/5,24 s; teste anterior do mesmo comando havia observado
202556 kB/5,35 s. Não há série suficiente para análise estatística de RAM.
Ainda faltam referência manual independente e mapa físico conferido para
cumprir a validação de acurácia e profundidade da pesquisa.

### Atualização — referência manual em branco e mapa físico na interface (16 de novembro de 2026)

O editor ganhou um modo de anotação que começa com todos os rótulos em zero
sobre o DICOM inteiro, sem mostrar máscaras do detector. `anotar_referencia.py`
e o botão **Anotar referência** salvam NPZs versionados e JSON de proveniência
em `referencias/`, marcados como pendentes de conferência independente.

Por solicitação do usuário, a interface agora oferece **Abrir lote existente**,
**Associar profundidades** e **Gerar curvas do lote**. O usuário classifica
cada ID como inserto, artefato, incerto ou não avaliado e digita a profundidade
em mm apenas quando tem evidência. `mapear_profundidades.py` versiona o mapa
e o vincula ao SHA-256 do CSV. As curvas físicas são uma etapa de análise
posterior, sem fornecer forma, número, grade ou profundidade ao detector.
O mapeamento pode ser parcial. `gerar_curvas_fisicas_lote.py` omite imagens
sem mapa ou inconclusivas e não inventa profundidades.

Teste sem mapas reais: zero curvas físicas, nove omissões explícitas. Com
mapas sintéticos **somente em `/tmp`**, 16 figuras análogas às Figuras 19–34,
sete imagens utilizáveis e exclusão de Tórax125_2/4; esses gráficos de teste
não têm interpretação física. Sete testes sintéticos passaram. A documentação
de uso está em `docs/MAPEAMENTO_PROFUNDIDADES.md`. Nenhum mapa real foi
preenchido: o usuário ainda precisa confirmar cada profundidade e os
contornos das máscaras.

### Atualização — reorganização do diretório radio2 (16 de novembro de 2026)

Por solicitação do usuário, os módulos de implementação foram agrupados no
pacote `radio2/`. Permanecem na raiz os comandos `main.py`, `interface.py` e
`processar_lote.py`, com as mesmas opções de CLI; ferramentas auxiliares são
executadas com `venv/bin/python -m radio2.<modulo>`. O código histórico foi
movido de `baseline/` para `docs/historico_codigo/`. Seis pastas de resultados
antigos foram agrupadas em `resultados/historico/`, com SHA-256 idêntico para
seus 178 arquivos. Os lotes ativos, revisões, DICOMs e referências não foram
movidos. Cópia de segurança do código anterior à reorganização:
`/tmp/radio2_codigo_antes_reorganizacao_2026-11-16.tar.gz`, SHA-256
`ccfcdb6b226bd796541667808bf687a5122c6fecdf2bf52f04cd9eb2ea19616a`.

Comparação reproduzível: `venv/bin/python processar_lote.py --dicom-dir dicom
--output-dir /tmp/radio2_reorganizado_lote_2026-11-16 --sensibilidade 1.5`.
Nos nove DICOMs, as contagens continuaram Crânio 24/23/24, Mão 24/24/23 e
Tórax 24/5/1. Todos os `resultados.csv` e arrays das máscaras NPZ foram
iguais aos de `resultados/lote_demonstracao_2026-11-16`; os estados de
qualidade foram iguais aos de `/tmp/radio2_qualidade_2026-11-16` (sete
provisórios e Tórax125_2/4 inconclusivos). O lote de demonstração antecede a
adição do estado de qualidade e, por isso, seus JSONs não são idênticos nesse
campo. Sete testes sintéticos passaram.

O comando `venv/bin/python -m radio2.gerar_resultados_tcc` com os argumentos
de `docs/RECRIACAO_GRAFICOS_TCC.md` gerou 20 PNGs em `/tmp`; os 20 hashes
foram idênticos aos de `resultados/recriacao_tcc_2026-11-16`. O HTML mudou
pelos links relativos para os CSVs de origem a partir da nova saída. Sem mapas físicos, o comando
`venv/bin/python -m radio2.gerar_curvas_fisicas_lote --lote
resultados/lote_demonstracao_2026-11-16 --saida
/tmp/radio2_curvas_sem_mapa_reorganizado_2026-11-16` gerou zero figuras.
A interface Tk não foi testada visualmente e não houve nova medição de RAM.
`git status` não pôde ser executado: `.git` está vazio e não é um repositório.

### Atualização — profundidade na revisão de máscaras (16 de novembro de 2026)

O usuário pediu associação de profundidade na mesma janela em que ajusta
contornos. O editor `radio2/editor_mascaras.py` agora mostra números dos
rótulos sobre a imagem e lista lateral; seleção por botão direito ou lista
exibe classe e profundidade editáveis ao lado da máscara. `Salvar e recalcular`
cria uma revisão da máscara e do CSV, transfere as associações pelos
`rotulos_origem` para os IDs possivelmente renumerados e salva mapa físico
versionado vinculado por SHA-256 ao CSV revisado. Se houver inserto mapeado,
gera curvas individuais. O gerador do lote agora usa a revisão mais recente
de cada imagem e omite uma revisão sem mapa, para não misturar medidas de
versões diferentes. A profundidade permanece fora do detector.

Comparação antes/depois: `venv/bin/python processar_lote.py --dicom-dir dicom
--output-dir /tmp/radio2_apos_profundidade_no_editor_2026-11-16
--sensibilidade 1.5`. Nos nove DICOMs, os CSVs, os arrays NPZ das máscaras e
os estados de qualidade foram iguais aos de
`/tmp/radio2_reorganizado_lote_2026-11-16`; contagens Crânio 24/23/24,
Mão 24/24/23 e Tórax 24/5/1. Oito testes sintéticos passaram. Uma revisão
real de `Crânio81_1` em `/tmp`, sem pixels alterados, recebeu duas
profundidades **artificiais apenas para testar o fluxo**; o mapa foi recarregado
pelos rótulos de origem, as curvas individuais foram criadas e o gerador de
lote produziu quatro figuras usando o CSV/mapa da revisão. Com o lote sem
mapas, zero curvas físicas foram geradas. A interface Tk não foi testada com
mouse porque o processo não conseguiu conectar ao display `:0`; também não
houve medição de pico de RAM nesta alteração.

### Atualização — reaproveitamento espacial de profundidades (16 de novembro de 2026)

Ao salvar uma revisão com mapa informado pelo usuário, o editor procura no
mesmo lote outras exposições cujo nome tem o mesmo prefixo antes do mAs (por
exemplo, `Mão46_1` → `Mão46_2`/`Mão46_4`). O módulo
`radio2/transferir_profundidades.py` associa centroides dos CSVs por uma
correspondência exclusiva 1:1, limitada a 25 px ou 30% do espaçamento típico
entre regiões, o menor dos dois. Não usa ordem de intensidade, grade,
quantidade-alvo, forma ou raio; ocorre somente após a detecção. Regiões sem
par permanecem `não avaliado`. Imagens inconclusivas (inclusive lotes antigos
sem campo de qualidade, mas com todos os candidatos alertados), dimensões
incompatíveis e mapas editados pelo usuário são omitidos. O JSON transferido
registra origem, SHA-256, pares, distâncias, omissões e pendência de
conferência visual. O relatório individual e o relatório do lote distinguem
mapas transferidos dos digitados pelo usuário. Digitar uma profundidade no
editor agora seleciona automaticamente a classe `inserto` quando ela ainda
está como `não avaliado`.

Métrica antes da alteração: nos CSVs da sensibilidade 1,5, associação
espacial exclusiva entre exposições 1→2/4 encontrou Mão 24/23 pares e Crânio
23/24 pares, com distâncias máximas de 1,74/2,48 px e 0,21/5,53 px,
respectivamente. Teste técnico depois da alteração: nove CSVs/JSONs do lote
`resultados/lote_demonstracao_2026-11-16` foram copiados para
`/tmp/radio2_transferencia_pos_refatoracao_2026-11-16`; mapas com
profundidades **artificiais** foram criados apenas em `/tmp` para as imagens
de 1 mAs. O programa preencheu Mão 2/4 com 24/23 classes e Crânio 2/4 com
23/24 classes, omitindo Tórax 2/4 como inconclusivos. Em teste separado,
um mapa editado manualmente no alvo não foi sobrescrito. O comando
`venv/bin/python -m radio2.gerar_curvas_fisicas_lote --lote
/tmp/radio2_transferencia_pos_refatoracao_2026-11-16 --saida
/tmp/radio2_curvas_transferidas_pos_refatoracao_2026-11-16` gerou 16 figuras
marcadas como experimentais. Nove testes sintéticos passaram com
`venv/bin/python -m unittest discover -s tests -v`. Nenhuma profundidade real
foi atribuída aos resultados do projeto; as correspondências transferidas
ainda exigem conferência do usuário. A interface gráfica continua sem teste
visual nesta sessão por falta de acesso ao display `:0`.

Verificação final do detector após a integração: `venv/bin/python
processar_lote.py --dicom-dir dicom --output-dir
/tmp/radio2_apos_transferencia_grupo_2026-11-16 --sensibilidade 1.5`.
Nos nove DICOMs, todos os CSVs, arrays das máscaras NPZ e estados de
qualidade foram idênticos aos de
`/tmp/radio2_apos_profundidade_no_editor_2026-11-16`; contagens Crânio
24/23/24, Mão 24/24/23 e Tórax 24/5/1. A comparação não mede acurácia
contra referências manuais nem precisão das profundidades transferidas.

Aplicação aos dados do usuário após os testes: foi encontrado no lote
`resultados/lote_20261116_154632` um mapa manual em
`002_Crânio81_2/revisoes/revisao_002`, com 24 classes `inserto` e 24
profundidades distintas de 1 a 24 mm. O mapa foi tratado como associação
informada pelo usuário, **não como verdade física validada**. Antes da
transferência, não havia mapas em `001_Crânio81_1` e `003_Crânio81_4`;
houve 24 correspondências exclusivas em cada alvo, com distâncias máximas
de 4,344 e 5,397 px. Executado:

```bash
venv/bin/python -m radio2.transferir_profundidades \
  resultados/lote_20261116_154632/002_Crânio81_2/revisoes/revisao_002
venv/bin/python -m radio2.gerar_curvas_fisicas_lote \
  --lote resultados/lote_20261116_154632 \
  --saida resultados/lote_20261116_154632/curvas_fisicas
```

Crânio 1 e 4 receberam mapas versionados de 24 insertos cada, marcados
`transferencia_espacial_automatica` e `conferencia_visual_pendente=true`.
O SHA-256 do mapa original de Crânio 2 permaneceu
`678c43648143677b47dbf004353801741eb0d853bc096c741535627033ad2887`.
O relatório gerou seis figuras e distingue os mapas transferidos do mapa
digitado; Mão e Tórax continuam sem mapas nesse lote. A correspondência
espacial e as curvas precisam de conferência humana antes de interpretação
física ou comparação com o TCC.

### Atualização — proposta de evolução e preparação para GitHub (16 de novembro de 2026)

O usuário considera separar a simulação do segmentador, melhorar a interface,
criar aplicativo compilado ou site e publicar no GitHub. Inspeção local:
`simulacao_xrmc/` ainda contém um cenário mínimo independente, 256×256,
50 keV monoenergético, uma perfuração passante; a saída existente passou em
`venv/bin/python simulacao_xrmc/validar_minimo.py
simulacao_xrmc/minimo_pmmaa_furo/output/image.npy`, com razão de transmissão
furo/PMMA 1,853070. Isso não valida a aquisição experimental. Todos os nove
DICOMs locais apresentam campos de identificação preenchidos e 46 tags
privadas cada; valores não foram impressos ou alterados. O atalho `.desktop`
usa caminho absoluto e o script XRMC depende de `../venv/bin/python`, pontos
de portabilidade a resolver antes de separar/renomear. `git status` continua
falhando porque `.git` está vazio.

Foi criada `.gitignore` para excluir DICOMs, resultados, referências,
`venv/`, dependências e saídas locais do XRMC, PDF do TCC e atalho local da
publicação inicial. Onze casos de inclusão/exclusão foram conferidos com Git
em um repositório temporário; `venv/bin/python -m unittest discover -s tests
-q` passou os nove testes. A proposta de arquitetura e sequência de trabalho
está em `docs/PROXIMOS_PASSOS.md`. Nenhum diretório foi renomeado nem
publicado no GitHub nesta etapa.
