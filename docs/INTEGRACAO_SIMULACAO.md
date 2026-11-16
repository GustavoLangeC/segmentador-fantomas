# Integração reproduzível entre XRMC e segmentador

**Data:** 16 de novembro de 2026.

## Contrato de arquivos

O repositório [simulacao-xrmc](https://github.com/GustavoLangeC/simulacao-xrmc)
gera `image.npy` (`float64`, 256×256, valores numéricos sem normalização),
`manifest.json`, `verdade_simulada.npz` (`labels` 2D da imagem inteira) e
`verdade_simulada.json` (método e hashes). A referência é a projeção ideal da
perfuração passante calculada nas duas faces da placa, usando raios centrais
e centros de pixel. O gerador de referência conhece a geometria do cenário;
o detector recebe apenas a imagem. O avaliador só carrega a referência depois
da detecção e verifica o SHA-256 da imagem.

O mesmo `PhantomSegmenter` e `InsertoDetector` usados no fluxo DICOM localizam
as regiões no NPY. O processamento usa `float32` para localizar, mas as médias,
dispersões e fundos são extraídos do array `float64` original. O recorte é
registrado para alinhar a referência de imagem inteira com a máscara detectada.

## Executar

Em `simulacao-xrmc`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./instalar_xrmc_local.sh  # apenas se o XRMC local ainda não estiver instalado
XRMC_PYTHON=.venv/bin/python ./executar_minimo.sh
```

Em `segmentador-fantomas`, com `venv/` preparado conforme o README:

```bash
venv/bin/python -m radio2.avaliar_simulacao \
  --imagem ../simulacao-xrmc/minimo_pmmaa_furo/output/image.npy \
  --referencia ../simulacao-xrmc/minimo_pmmaa_furo/output/verdade_simulada.npz \
  --saida resultados/avaliacao_simulada --sensibilidade 1.5
```

`resultados.csv` preserva sinal bruto, fundo local, sinal corrigido, área e
ruído; `mascaras.npz` contém as regiões previstas; `avaliacao_referencia.json`
contém TP, FP, FN, IoU, Dice e erro de centroide. `comparacao.png` e
`relatorio_simulacao.html` mostram as diferenças de máscara e as medições.
A saída deve estar ausente ou vazia para evitar sobrescrever resultados.

## Resultado observado neste cenário

Com o cenário mínimo de 50 keV monoenergético e sensibilidade 1,5, o comando
detectou uma região: **TP=1, FP=0, FN=0**, IoU por pixel **0,874508**,
2.287 pixels previstos e 2.000 na referência geométrica. A diferença se
concentra na borda; o erro de centroide associado foi **0,0354 px**. A
transmissão furo/PMMA do XRMC foi **1,853070**. Uma execução do avaliador
teve VmHWM observado de **124912 kB** e duração de **1,191 s**; é uma amostra,
não uma comparação estatística de memória.

A referência expressa a geometria ideal, não uma máscara manual conferida
pixel a pixel. Penumbra, amostragem e resposta simulada podem deslocar a
borda visível. O caso tem uma única perfuração circular passante e não mede
generalização para outras formas, profundidades ou DICOMs reais. O simulador
não reproduz quantitativamente o equipamento radiográfico do TCC.

## Regressão nos DICOMs existentes

Antes e depois da integração foi executado:

```bash
venv/bin/python processar_lote.py --dicom-dir dicom \
  --output-dir /tmp/radio2_integracao_before_2026-11-16 --sensibilidade 1.5
venv/bin/python processar_lote.py --dicom-dir dicom \
  --output-dir /tmp/radio2_integracao_after_2026-11-16 --sensibilidade 1.5
```

Nos nove arquivos, `resultados.csv` foi idêntico em bytes e os arrays de
`mascaras.npz`, os recortes e os estados de qualidade foram iguais. Contagens:
Crânio **24/23/24**, Mão **24/24/23**, Tórax **24/5/1**. Tórax125_2/4
permaneceram inconclusivos. Essa comparação demonstra ausência de regressão
nesse conjunto, não acurácia contra anotações independentes.
