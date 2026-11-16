# Linha de base do detector genérico — 16 de novembro de 2026

## Objetivo

Registrar uma execução reproduzível do detector atual antes de modificá-lo. Os
resultados abaixo descrevem a saída automática; não são métricas de acurácia,
pois ainda não há máscara manual independente para estes DICOMs.

## Ambiente e comandos

Foram executados os testes sintéticos e, para cada arquivo DICOM, o comando:

```bash
venv/bin/python main.py <arquivo> --sem-grafico --sensibilidade 1.5 \
  --output-dir resultados/historico/linha_base_2026-11-16_sensibilidade_1.5/<arquivo>
```

Os testes foram executados com:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Resultado: 3 testes sintéticos aprovados. Eles exercitam formas retangular,
barra e L, bem como associação com FP/FN; não medem desempenho nos DICOMs.

## Saídas preservadas

Cada subdiretório de
`resultados/historico/linha_base_2026-11-16_sensibilidade_1.5/` contém:

- `resultados.csv` e `resultados.json`, com sinais e alertas por região;
- `coordenadas.csv`;
- `mascaras.npz`, com rótulos por instância e bbox do recorte.

Também foram geradas visualizações para a revisão inicial de `Mão46_1`,
`Tórax125_2` e `Tórax125_4`, no próprio subdiretório de cada imagem.

Na raiz desse diretório, `metadados_dicom.csv` e `metadados_dicom.json`
documentam os nove arquivos sem exportar identificação de paciente. A tabela
confirma imagens CR MONOCHROME2, 12 bits armazenados em 16 bits, adquiridas no
Philips DigitalDiagnost C50; o campo `Exposure` é 1/2/4 para cada técnica.

## Resumo descritivo

| DICOM | Regiões automáticas | Regiões com alerta | Alerta de contraste local baixo | Maior área (px) |
|---|---:|---:|---:|---:|
| Crânio81_1 | 24 | 2 | 2 | 4.836 |
| Crânio81_2 | 23 | 1 | 1 | 4.847 |
| Crânio81_4 | 24 | 2 | 2 | 5.431 |
| Mão46_1 | 25 | 5 | 5 | 4.905 |
| Mão46_2 | 24 | 3 | 3 | 4.902 |
| Mão46_4 | 23 | 1 | 1 | 4.899 |
| Tórax125_1 | 24 | 2 | 2 | 5.206 |
| Tórax125_2 | 5 | 5 | 2 | 195.007 |
| Tórax125_4 | 1 | 1 | 1 | 1.834 |

## Observações que orientam a próxima fase

- `Mão46_1`: o par `R005` (421 px) e `R010` (3.274 px) recebeu alerta
  mútuo de possível fragmento. A visualização mostra componentes na mesma
  posição aproximadamente à esquerda. Isto é uma hipótese de fragmentação a
  ser avaliada contra anotação manual, e não uma regra de mesclagem já aceita.
- `Tórax125_2`: `R002` ocupa 195.007 px, recebeu alerta de proximidade da área
  máxima e está associado a quatro alertas de possível duplicata. Na revisão
  visual, a máscara acompanha uma ampla região de fundo, portanto esta saída
  deve ser tratada como falha de aceitação, não como inserto confirmado.
- `Tórax125_4`: a única região possui CNR local heurístico de aproximadamente
  0,40 e alerta de contraste local baixo. Não deve ser interpretada como
  detecção confiável sem referência externa.
- As contagens 24, 25, 23, 5 e 1 não identificam objetos físicos nem provam
  qualidade de segmentação. A referência manual será usada somente para
  avaliação por IoU e associação global.

## Próxima ação mensurável

Criar máscaras manuais por instância para `Crânio81_1`, `Mão46_1` e
`Tórax125_2`, seguindo `docs/AVALIACAO_SEGMENTACAO.md`. Depois, executar
`--referencia` para obter TP, FP, FN, precisão, revocação, F1, Dice/IoU e
erro de centroide antes de alterar qualquer limiar ou regra do detector.
