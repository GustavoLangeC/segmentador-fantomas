# Correção localizada de fragmentos — Mão46_1

**Data:** 16 de novembro de 2026.

## Causa observada

Com `--sensibilidade 1.5`, duas máscaras da mesma polaridade ocupavam a
mesma região à esquerda do recorte: R005 (421 px) e R010 (3274 px). As
máscaras refinadas tinham 102 pixels em comum. O programa as media como dois
objetos; ao exportar rótulos, a segunda sobrescrevia o trecho compartilhado
da primeira. Isso explicava os contornos duplicados e o rótulo extra na figura.

## Alteração

Após o refinamento e antes das medições, o detector une uma máscara pequena
à maior somente quando ambas têm a mesma polaridade, a menor tem até 25% da
área da maior, suas caixas se sobrepõem substancialmente e pelo menos 10% da
menor coincide com a outra máscara. A união usa as máscaras reais. Não usa
quantidade de objetos, grade, circularidade nem posição esperada.

## Comandos de reprodução

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python main.py Mão46_1 --sem-grafico --sensibilidade 1.5 \
  --output-dir resultados/historico/apos_mescla_2026-11-16_s1.5/Mão46_1
venv/bin/python main.py Mão46_1 --sem-grafico --sensibilidade 1.2 \
  --output-dir resultados/historico/apos_mescla_2026-11-16_s1.2/Mão46_1
```

O mesmo comando com `--sensibilidade 1.5` foi executado nos outros oito
DICOMs, cada um no respectivo subdiretório de
`resultados/historico/apos_mescla_2026-11-16_s1.5/`. A imagem de Mão foi gerada com
`--sem-janela` dentro de seu subdiretório.

## Antes e depois

| Observação | Antes | Depois |
|---|---:|---:|
| Regiões em Mão46_1, sensibilidade 1,5 | 25 | 24 |
| Objetos com alerta de possível fragmento | 2 | 0 |
| Área da máscara unida | 421 e 3274 px, com 102 px de interseção | 3593 px |
| Diferença de pixels de primeiro plano | — | 0; a união não adicionou nem removeu pixels detectados |
| Regiões em Mão46_1, sensibilidade 1,2 | 26 | 26 |
| Testes sintéticos | 3 existentes | 4 aprovados, incluindo mesclagem de formas retangulares |

Nos outros oito DICOMs, contagens e máscaras em sensibilidade 1,5 ficaram
idênticas (IoU pareado mínimo 1,0 e zero diferença de primeiro plano). A
imagem `resultado_Mão46_1.png` após a mudança mostra um único rótulo na
região anteriormente dividida. A comparação automática em
`resultados/historico/revisao_apos_mescla/Mão46_1/` ainda marca quatro regiões para
revisão e dois candidatos presentes apenas na sensibilidade 1,2.

## Limite da conclusão

A correção elimina uma duplicação demonstrável, mas não determina quais
regiões fracas são insertos físicos. A imagem de Mão continua com contraste
local baixo nas regiões à esquerda. Sem máscara externa conferida, não há
precisão, revocação, falso positivo ou falso negativo medido; 24 não é uma
contagem-alvo imposta pelo algoritmo.
O pico de memória desta revisão não foi medido: `/usr/bin/time` não está
disponível neste ambiente. A mesclagem usa somente janelas locais das duas
máscaras envolvidas; não cria cópias completas da imagem para cada par.
