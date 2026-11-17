# Guia para explicar o segmentador e a simulação ao professor

**Estado do projeto em 16 de novembro de 2026.** Este texto descreve o código
que está nos repositórios e os testes reproduzidos até esta data. Leia também
[`INTEGRACAO_SIMULACAO.md`](INTEGRACAO_SIMULACAO.md),
[`AUDITORIA_MAPAS_FISICOS_2026-11-16.md`](AUDITORIA_MAPAS_FISICOS_2026-11-16.md)
e [`TAREFA_MASCARAS_MANUAIS.md`](TAREFA_MASCARAS_MANUAIS.md).

## Explicação de um minuto

> O programa recebe radiografias DICOM de fantomas e procura insertos por
> contraste local, sem receber número, grade, posição, raio ou forma dos
> furos. Primeiro recorta o fantoma externo; depois estima o fundo da imagem,
> encontra componentes claros e escuros e refina cada máscara. Mede área,
> centroide, sinal bruto, ruído e fundo nos pixels originais, além de calcular
> uma correção experimental e RSR/RCR. A profundidade física é associada
> posteriormente, por informação externa. Um segundo repositório gera imagens
> simuladas e referências conhecidas para testar o mesmo detector. O fluxo
> técnico funciona; a acurácia nos DICOMs reais ainda precisa de máscaras
> manuais independentes.

## 1. Pergunta de pesquisa e três tarefas distintas

1. **Detecção:** onde há regiões contrastantes no DICOM e qual é a máscara de
   cada uma? O detector não recebe a geometria conhecida do fantoma.
2. **Medição:** quanto valem o sinal, fundo, ruído, área e centroide de cada
   região detectada? Os valores são medidos sobre `pixel_array` original.
3. **Identificação e validação:** a qual perfuração e profundidade física uma
   região corresponde? A máscara automática concorda com uma anotação humana
   independente? Essas respostas exigem dados externos e não são deduzidas
   do brilho nem do número de objetos.

Uma contagem de 24 regiões não prova 24 acertos: pode haver falsos positivos
e falsos negativos que se compensam. A avaliação científica exige máscaras
independentes e, para curvas físicas, um mapa de profundidades conferido.

## 2. Organização dos dois programas

```text
simulacao-xrmc/                    segmentador-fantomas/
  cenário XRMC mínimo                 main.py: entrada DICOM individual
  cenários analíticos                 processar_lote.py: nove ou outros DICOMs
  image.npy ----------------------->  segmentador_fantomas/segmentacao.py
  verdade_simulada.npz ----------->  avaliador, só depois da detecção
  manifestos e hashes                 interface.py: fluxo gráfico
                                       CSV, NPZ, JSON, PNG e HTML
```

O pacote Python atual é `segmentador_fantomas/`. O pequeno pacote `radio2/`
mantém comandos antigos `python -m radio2.modulo` funcionando. A pasta local
`~/projects/radio2` também é um link para `~/projects/segmentador-fantomas`.
Os repositórios públicos são [segmentador-fantomas](https://github.com/GustavoLangeC/segmentador-fantomas)
e [simulacao-xrmc](https://github.com/GustavoLangeC/simulacao-xrmc).
DICOMs, resultados reais, referências, ambiente virtual e PDF do TCC não
foram publicados.

## 3. O caminho de um DICOM pelo código

### 3.1 Leitura e recorte externo

`DicomReader` usa `pydicom.dcmread` e `pixel_array`. A entrada deve ser 2D.
As nove imagens locais são radiografias CR MONOCHROME2 com 12 bits armazenados
em 16 bits; o código lê o cabeçalho de cada arquivo em vez de supor que todo
DICOM terá essas propriedades. Não inverte nem normaliza os pixels usados nas
medições. Uma cópia `float32`, normalizada entre os percentis 1 e 99, serve
somente para localizar a placa e gerar prévias.

`PhantomSegmenter.detect` aplica desfoque gaussiano, vários percentis de
limiar e ambas as polaridades, morfologia e contornos. Escolhe uma região
externa aproximadamente retangular por critérios relativos de área,
dimensões e retangularidade, depois recua a máscara interna cerca de 1,2%.
Essa hipótese geométrica vale para **a borda externa da placa** observada;
ela não exige que os **insertos** sejam círculos ou sigam grade. Se a placa
externa não puder ser localizada, o programa informa falha.

### 3.2 Candidatos genéricos a insertos

`InsertoDetector.detect` trabalha dentro da máscara do fantoma, recuada da
borda. Suaviza uma cópia para localização e estima um fundo 2D com filtros
gaussianos normalizados pela máscara válida:

```text
F(x,y) = Gσ * (I·M) / (Gσ * M)
R(x,y) = I_suavizada(x,y) − F(x,y)
ruído_robusto = 1,4826 · mediana(|R − mediana(R)|)
```

`Gσ` é o filtro gaussiano, `M` indica a área interna válida e `R` é o
resíduo local. Esse resíduo é procurado nas duas polaridades: objetos mais
claros ou mais escuros que o entorno. Pixels de semente precisam exceder
`sensibilidade × ruído_robusto`; o crescimento usa metade desse limiar.
Depois vêm abertura morfológica, preenchimento de buracos e componentes
conectados. A área mínima padrão é `max(25, 0,00018 × área_interna)` pixels;
a máxima é `0,15 × área_interna`. São filtros relativos de candidatos, não
um raio ou número de insertos esperado. A opção `--min-area` substitui a
área mínima automática. Sensibilidade menor tende a encontrar contrastes
mais fracos e também pode criar mais falsos positivos.

Cada componente é refinado localmente: o programa ajusta uma superfície
polinomial suave de seis termos ao fundo fora da semente, amostrando até
aproximadamente 4.000 pixels e rejeitando discrepantes em três iterações.
Depois cresce a máscara sobre o contraste em relação a esse fundo local.
Fragmentos pequenos só são mesclados se houver sobreposição real de máscaras
da mesma polaridade. Nem a forma nem a posição nominal de um furo é imposta.

### 3.3 Medidas nos pixels originais

Após localizar a máscara, o programa usa os valores **não suavizados** do
DICOM. Para o sinal da ROI, prefere o núcleo erosionado dois pixels, evitando
que bordas difusas dominem a média; se o núcleo ficar pequeno demais, usa a
máscara inteira. O sinal bruto `S` é a média desse núcleo e `σ_ROI` é seu
desvio padrão. A área corresponde à máscara completa; o centroide vem dos
pixels rotulados. Se o DICOM fornecer `PixelSpacing`, a área em mm² é área
em pixels multiplicada pelo produto dos espaçamentos; sem esse metadado,
o programa não inventa escala física.

O fundo local `F_i` é a **mediana** num anel ao redor da máscara, excluindo
os demais objetos e a borda inválida. O desvio padrão dos pixels desse anel
é `σ_fundo`. A mediana protege contra algumas contaminações, mas o anel ainda
pode ser inadequado em imagens ruins. Sem amostras suficientes, o fundo é
indisponível e o objeto recebe alerta.

### 3.4 Correção e indicadores

```text
F_ref = mediana dos fundos locais válidos
S_corrigido = (S_bruto / F_i) × F_ref
contraste_relativo (%) = 100 × (S_bruto / F_i − 1)
RSR = S_bruto / σ_ROI
RCR = |S_bruto − F_i| / σ_fundo
```

Esses valores ficam **lado a lado** no CSV; a correção não substitui o sinal
bruto. Divisão por fundo ou desvio padrão inválido gera valor ausente, não
uma medição fabricada. O TCC de William da Veiga usa como referência o fundo
da ROI central 12 e mede o fundo em regiões acima/abaixo da ROI, depois de
inverter a escala de cinza para sua análise. Nosso código usa a mediana dos
fundos locais de anéis e preserva os pixels DICOM originais. Portanto, a
fórmula atual é **uma adaptação experimental**, não a reprodução literal do
TCC nem prova de eliminação do efeito anódico. Gradientes também podem ter
outras causas, como resposta do detector, bordas e processamento da imagem.

`rank_bruto` e `rank_corrigido` ordenam os sinais; `region_id` (`R001`, etc.)
segue a posição espacial dos centroides. Nenhum deles é profundidade física.
Trocas de rank já foram observadas, inclusive em Crânio81_4.

### 3.5 Alertas e falha segura

`object_quality` sinaliza fundo indisponível, CNR local abaixo de 1,5,
área perto dos limites e pares possivelmente fragmentados/duplicados. CNR
local é `|S−F_i| / √(σ_ROI²+σ_fundo²)`. São heurísticas, **não** probabilidades
calibradas. O detector não remove candidatos só para completar uma contagem.

`image_quality` devolve `inconclusiva` se nada foi encontrado, se todos os
candidatos têm alerta ou se há pelo menos cinco candidatos e menos de 20%
estão sem alerta. O último critério foi adicionado após um teste de baixo
contraste que produziu muitos candidatos espúrios. Ele é conservador e ainda
precisa de calibração com referências independentes. Nos demais casos, o
estado é `provisoria`, nunca “validada”. Tórax125_2 e Tórax125_4 permanecem
inconclusivos no lote local de sensibilidade 1,5.

## 4. Executar, revisar e interpretar os arquivos

```bash
cd ~/projects/segmentador-fantomas
venv/bin/python main.py Crânio81_1 --sem-janela --output-dir resultados/exemplo
venv/bin/python processar_lote.py --dicom-dir dicom \
  --output-dir resultados/lote_novo --sensibilidade 1.5
venv/bin/python interface.py
```

`main.py` mantém opções `--sensibilidade`, `--min-area`, `--sem-janela`,
`--sem-grafico`, `--matplotlib`, `--output-dir`, `--referencia` e
`--iou-minimo`. `--sem-grafico` evita PNG/HTML e imprime números; com
`--output-dir` ainda exporta CSV/JSON/NPZ. O lote processa sequencialmente,
registra falhas por arquivo e não interrompe automaticamente os demais.
Na interface, é possível processar DICOMs, abrir relatórios, editar máscaras,
informar profundidades e gerar curvas. O atalho instalado no menu chama
`iniciar_segmentador.sh`, que abre essa mesma interface; não é um programa
compilado nem um website.

| Arquivo de saída | Conteúdo e uso |
| --- | --- |
| `resultados.csv` | Uma linha por região: área, centroide, sinal bruto, fundo, correção, ruído, RSR/RCR, ranks e alertas. |
| `mascaras.npz` | Array `labels` 2D: 0 = fundo, inteiros positivos = regiões; inclui bbox do recorte. |
| `resultados.json` | Parâmetros, qualidade, bbox e medidas estruturadas. |
| `resultado_*.png` | Visualização de contornos e máscaras, sem alterar os dados. |
| `relatorio_*.html` | Quatro gráficos e tabela individual. |
| `resumo_lote.csv/json` | Situação de cada imagem de um lote. |
| `avaliacao_referencia.json` | TP/FP/FN, IoU/Dice e erro de centroide, **somente se houve referência**. |

O editor de máscaras salva uma nova revisão, recalcula as medidas no DICOM
original e preserva o resultado anterior. A associação de classe e
profundidade é feita na própria janela de revisão. Ao salvar um mapa de uma
exposição, o sistema pode sugerir associações para outras exposições da
mesma técnica por centroides próximos, únicos e compatíveis. O limite é
`min(25 px, 30% do espaçamento típico)`; imagens inconclusivas e mapas já
editados pelo usuário não são sobrescritos. Toda transferência é posterior à
detecção e marcada como pendente de conferência.

Existem dois tipos de gráfico que não devem ser confundidos:

- `gerar_resultados_tcc.py` cria **figuras análogas** às do TCC para o conjunto
  conhecido; eixos de objeto usam ID espacial ou associação provisória.
- `gerar_curvas_fisicas_lote.py` usa profundidades **informadas pelo usuário**
  em mapas versionados e ligados por SHA-256 ao CSV. O código de relatório
  reconhece nomes/técnicas do conjunto do TCC; isso não é requisito do
  detector genérico.

O mapa atual de Crânio81_2 tem 1–24 mm informados pelo usuário e foi
transferido para Crânio81_1/4. Os três mapas têm `validacao_independente=false`;
os dois transferidos ainda pedem conferência visual. O TCC declara excluir o
furo de 24 mm, mas também menciona 24 ROIs. A correspondência precisa ser
resolvida com o orientador ou documentação da placa antes de usar essas
curvas como resultado físico conclusivo.

## 5. Simulação: dois níveis com finalidades diferentes

### 5.1 XRMC mínimo

`simulacao-xrmc/executar_minimo.sh` usa XRMC 6.7.0 com PMMA de 25 mm,
uma perfuração passante circular de 10 mm, filtro de Al de 2 mm, distância
fonte-detector de 100 cm, detector 256×256 com pixel de 0,02 cm, fonte
monoenergética de 50 keV e sem espalhamento. Salva `image.dat`, converte
sem normalizar para `image.npy` `float64` e cria uma prévia PNG apenas para
exibição. O cenário é uma **verificação física mínima**, não uma reprodução
do Philips DigitalDiagnost C50, nem de 46/81/125 kVp ou mAs clínicos.

`gerar_referencia.py` projeta a geometria conhecida da perfuração nas duas
faces da placa por raios centrais e centros de pixel. Salva
`verdade_simulada.npz` e um JSON com hashes da imagem e do manifesto. Essa
“verdade” é geométrica do modelo ideal; penumbra e amostragem podem deslocar
a borda visível. O segmentador lê só `image.npy` para detectar, verifica o
hash e lê a referência **após** gerar sua máscara. O avaliador associa
instâncias por IoU máximo com atribuição global; por padrão, uma associação
conta como TP se IoU ≥ 0,5. Os não associados viram FP e FN.

Na execução atual: transmissão média furo/PMMA **1,853070**, uma região
detectada, **TP=1, FP=0, FN=0**, IoU por pixel **0,874508**. A referência
tinha 2.000 pixels e a previsão 2.287; grande parte da diferença está na
borda. Esse é o resultado de **um** cenário, não uma estimativa de acurácia
nos DICOMs reais.

### 5.2 Cenários analíticos de estresse

`gerar_cenario_analitico.py` produz imagens `float64` com formas e
profundidades configuradas por JSON. O sinal é ilustrativamente
`S=(S_PMMA+gradiente)·exp(μ·profundidade_cm)+ruído`; um teto opcional simula
perda de contraste por saturação. O `μ=0,24 cm⁻¹`, o sinal base e o ruído
são parâmetros de demonstração, **não calibrados** com o equipamento real.
As configurações são `quatro_formas` (círculo, retângulo, elipse e L; 5,
10, 15 e 20 mm), `baixo_contraste` e `saturacao`. A geometria e profundidade
ficam apenas no gerador e na avaliação externa. Misturar forma e profundidade
em uma série não permite atribuir uma tendência de sinal só à profundidade.

| Cenário, sensibilidade 1,5 | TP | FP | FN | IoU por pixel | Qualidade |
| --- | ---: | ---: | ---: | ---: | --- |
| Quatro formas | 4 | 0 | 0 | 0,836329 | provisória |
| Baixo contraste | 2 | 44 | 0 | 0,223424 | inconclusiva |
| Saturação ilustrativa | 0 | 5 | 2 | 0 | inconclusiva |

Os dois últimos resultados são **falhas demonstradas**. A classificação
inconclusiva alerta o usuário e não apaga FP. A interface agora oferece
**Simular e avaliar** com esses cenários ou o XRMC mínimo, além de
**Avaliar NPY existente**. Os relatórios mostram sobreposição, FP, FN,
medições originais e tabela de profundidades conhecidas da simulação
associadas somente após a detecção.
O comando `python -m segmentador_fantomas.benchmark_simulacao` executa os
quatro cenários sequencialmente e cria `resumo.csv/json` e `index.html` com
links para relatórios e logs. Ele reproduziu a tabela acima, mas não substitui
uma avaliação em imagens reais.

## 6. Estado das imagens reais e o que falta para validar

No lote local de sensibilidade 1,5, as contagens foram Crânio **24/23/24**,
Mão **24/24/23** e Tórax **24/5/1** para 1/2/4 mAs. Tórax125_2 e
Tórax125_4 ficaram inconclusivos; os outros sete tiveram avaliação técnica
provisória. CSVs, máscaras e estados de qualidade permaneceram iguais numa
comparação antes/depois desta mudança nos nove arquivos: `resultados.csv`
idênticos em bytes, arrays de máscaras e recortes iguais e o mesmo estado
de qualidade. Isso verifica ausência de regressão nesse conjunto, não
acurácia de segmentação.

**Ainda não há máscaras manuais independentes aceitas para os nove DICOMs.**
A tarefa foi preparada em [`TAREFA_MASCARAS_MANUAIS.md`](TAREFA_MASCARAS_MANUAIS.md)
para ser executada por anotador e revisor humanos. Quando chegarem, o código
valida formato e hash, calcula TP, FP, FN, precisão, revocação, F1, IoU/Dice
e erro de centroide. Até lá, não diga que a acurácia real foi validada.

## 7. Perguntas prováveis e respostas objetivas

**O detector é realmente genérico?** Ele não recebe a contagem, grade,
posição, raio ou forma dos insertos. Detecta por contraste local e
componentes conectados. A generalização ainda precisa ser **testada** em
mais fantomas reais; os cenários analíticos são apenas um teste inicial.

**Mas o código não supõe um retângulo?** Supõe uma região externa
aproximadamente retangular para recortar a placa conhecida. A liberdade de
forma é exigida para os insertos; não há filtro de circularidade neles.

**Por que não HoughCircles ou grade 5×5?** Esses métodos imporiam círculo,
raio e/ou disposição antecipada. O objetivo atual é detectar o que a imagem
sustenta, inclusive falhar quando falta contraste.

**Por que usar os pixels brutos?** Normalização e suavização mudam a escala
e a variância. Elas ajudam a localizar, mas sinal, ruído e RSR/RCR devem
descrever os valores originais disponíveis no DICOM.

**O sinal corrigido elimina o efeito anódico?** Não demonstramos isso. É uma
razão de sinal/fundo local com referência mediana, diferente da ROI 12 do
TCC. Pode reduzir parte de um gradiente, mas a causa e a correção efetiva
precisam de teste controlado.

**O que são `R001` e rank?** `R001` é um ID espacial da execução. Rank bruto
e corrigido ordenam intensidades. Nenhum é número físico do furo ou
profundidade; a ordem pode inverter.

**Como uma profundidade entra no sistema?** A pessoa informa classe e
profundidade em mm na revisão. O mapa é versionado e ligado ao CSV por
SHA-256. O algoritmo só pode sugerir transferência entre exposições por
posição; exige conferência humana.

**Por que 24 regiões não é 100% de acerto?** Contagem igual não identifica
quais foram encontradas. Um FP e um FN podem deixar a contagem igual.
Precisamos comparar máscaras com referências independentes.

**O que significam TP, FP, FN e IoU?** TP é uma região prevista associada a
uma região de referência com IoU acima do limiar; FP é prevista sem par;
FN é referência sem par. IoU é interseção/união de pixels das máscaras.
IoU por pixel e média dos IoUs das associações são grandezas distintas.

**Por que a IoU do XRMC não foi 1?** A referência representa projeção
geométrica ideal; a máscara detectada segue contrastes da imagem simulada,
incluindo borda difusa e amostragem. Houve 287 pixels a mais na previsão;
isso exige inspeção, não prova automática de erro do modelo ou detector.

**O XRMC reproduz o equipamento usado por William?** Não. O caso atual é
monoenergético a 50 keV, sem espalhamento e sem resposta calibrada do
detector. Verifica integração e sentido da transmissão num cenário mínimo.

**Por que há outra simulação, a analítica?** Ela permite variar forma,
profundidade, gradiente, ruído e saturação de modo controlado e reproduzível.
É um teste de software, mais simplificado que o XRMC, não uma validação
física ou clínica.

**O programa funciona com qualquer DICOM?** Aceita uma imagem DICOM 2D
legível, mas não garante detecção útil em qualquer exposição, modalidade ou
fantoma. Uma entrada fora desse domínio pode falhar ou ser inconclusiva.

**Como evitam consumo excessivo de memória?** Usam `float32` em imagens de
trabalho, preservam o array bruto para medir, limitam a regressão local a
aproximadamente 4.000 amostras e processam DICOMs sequencialmente. Uma
execução anterior de `Crânio81_1` observou VmHWM ao redor de 202 MB; isso
não é garantia universal de pico de RAM.

**O que está pendente para concluir a pesquisa?** Máscaras independentes,
conferência documental do mapa físico, comparação quantitativa em diferentes
exposições e fantomas, calibração da simulação e análise de incerteza. O
aplicativo local já abre por atalho, mas não há build compilado nem website.

## 8. Demonstração de cinco minutos

1. Abra a interface pelo menu **Segmentador de Fantomas** ou por
   `venv/bin/python interface.py`. Mostre um lote existente e os estados
   `provisoria`/`inconclusiva`, sem apresentar contagem como acurácia.
2. Abra uma imagem e seu `relatorio_*.html`; mostre sinal bruto, fundo,
   corrigido, RSR/RCR e os alertas lado a lado.
3. Abra **Revisar máscara e profundidade**; mostre que a profundidade é
   digitada **depois** da detecção e que salvar cria revisão, sem alterar a
   execução automática anterior.
4. Na seção **Simulação e avaliação**, escolha **Quatro formas (analítico)**,
   execute e mostre o relatório com TP/FP/FN e sobreposição visual. Depois
   explique a linha de baixo contraste como limite/falha transparente.
5. Mostre o protocolo de anotação humana e diga exatamente o que falta para
   afirmar acurácia nos DICOMs reais.

## 9. Frases que evitam conclusões indevidas

- Diga **“encontrou 24 candidatos”**, não “identificou os 24 furos físicos”.
- Diga **“estado técnico provisório”**, não “segmentação validada”.
- Diga **“correção experimental do fundo local”**, não “removeu o efeito anódico”.
- Diga **“profundidade informada ou transferida, pendente de conferência”**,
  não “profundidade descoberta pela imagem”.
- Diga **“IoU 0,875 no cenário XRMC mínimo”**, não “acurácia de 87,5% nos
  DICOMs”.
