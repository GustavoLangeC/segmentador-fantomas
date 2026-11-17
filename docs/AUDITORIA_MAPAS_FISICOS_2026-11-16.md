# Auditoria técnica dos mapas de profundidade existentes

**Data:** 16 de novembro de 2026. **Lote:** `resultados/lote_20261116_154632`.

Esta conferência usa `latest_measurements` e `load_current_map`, que verificam
o vínculo SHA-256 entre mapa e CSV. Ela verifica **integridade e associação
espacial**, não identifica fisicamente as perfurações nem aprova suas
profundidades.

| Imagem | Origem do mapa | Profundidades | Pares transferidos | Maior distância | Estado |
| --- | --- | ---: | ---: | ---: | --- |
| Crânio81_1 | transferência de Crânio81_2 | 24 (1–24 mm) | 24 | 4,344 px | conferência visual pendente |
| Crânio81_2 | informada pelo usuário em `revisao_002` | 24 (1–24 mm) | — | — | validação independente ausente |
| Crânio81_4 | transferência de Crânio81_2 | 24 (1–24 mm) | 24 | 5,397 px | conferência visual pendente |
| Mão46_1/2/4 | sem mapa | — | — | — | nenhuma profundidade atribuída |
| Tórax125_1/2/4 | sem mapa | — | — | — | nenhuma profundidade atribuída |

Os mapas carregaram sem erro de SHA-256. O registro de transferência indica
24 pares exclusivos em cada alvo, sem regiões sem correspondência. Isso
mostra que os centroides são próximos dentro do limite do algoritmo; não
prova que os rótulos de Crânio81_2 estavam fisicamente corretos. O campo
`validacao_independente` é `false` nos três mapas.

O TCC consultado descreve profundidades de 0 a 24 mm, declara usar 1 a 23 mm
e excluir a perfuração de 24 mm por atravessar a placa, mas também menciona
24 ROIs. O mapa atual usa 1 a 24 mm. Essa discrepância exige conferência com
o fantoma, caderno experimental ou orientador **antes** de interpretar curvas
como função de profundidade física. Não corrigir a lista automaticamente por
ordem de sinal ou posição.

Depois da conferência física, abra cada imagem transferida em **Revisar máscara
e profundidade**, corrija as associações se necessário e salve nova revisão.
As máscaras manuais independentes para medir FP/FN seguem a tarefa separada em
[`TAREFA_MASCARAS_MANUAIS.md`](TAREFA_MASCARAS_MANUAIS.md).
