# Próximos passos para o projeto

**Proposta para discussão — 16 de novembro de 2026.**

**Atualização:** a integração mínima e a separação em repositórios foram
implementadas em 16 de novembro de 2026; veja
[`INTEGRACAO_SIMULACAO.md`](INTEGRACAO_SIMULACAO.md). As demais etapas deste
documento continuam como propostas de pesquisa e produto.

## Organização sugerida

Separar em dois projetos irmãos, com responsabilidades explícitas:

```text
segmentador-fantomas/   análise DICOM, máscaras, medições e relatórios
simulacao-xrmc/         cenários físicos, execução XRMC e imagens simuladas
```

Um contrato de arquivos liga os dois projetos. O simulador exporta a matriz
numérica original (`imagem.npy`), um `manifest.json` com unidades, geometria,
espectro, detector e parâmetros aleatórios, e uma máscara de referência
(`verdade_simulada.npz`) gerada da geometria conhecida. O segmentador recebe
somente a imagem e seus metadados necessários para interpretar escala; a
referência entra depois, no avaliador de FP/FN, IoU e diferenças de sinal.
Esse contrato mantém o detector genérico sem número, grade ou forma de furos.

Antes de mover diretórios, tornar portáteis o atalho `.desktop`, o script XRMC
que usa `../venv/bin/python` e os caminhos absolutos nos resumos dos lotes.
Preservar as saídas atuais ou migrá-las com um script verificável. O nome
`segmentador-fantomas` descreve melhor o código atual que `radio2`; a troca do
nome do pacote Python exige atualização de imports, CLI e testes.

## Ordem de desenvolvimento

1. **Integração mínima:** executar o cenário XRMC atual, enviar sua imagem
   numérica ao mesmo núcleo do detector DICOM e comparar a máscara detectada
   com a máscara de referência simulada. Registrar escala de pixel, contraste,
   parâmetros e limitações no relatório. A imagem atual tem 256×256 pixels e
   espectro monoenergético de 50 keV; os DICOMs experimentais têm cerca de
   1450×1480 pixels. A diferença de escala precisa ser tratada explicitamente.
2. **Simulação útil para pesquisa:** variar profundidade, número e forma dos
   insertos, ruído e gradiente; depois testar espectros policromáticos e
   resposta do detector com parâmetros documentados. Comparar tendências de
   contraste e falhas do segmentador, sem afirmar reprodução do equipamento
   clínico até haver calibração independente.
3. **Interface:** mostrar lote, imagem, máscara, alertas e curvas em um fluxo
   único; oferecer fila de casos incertos, comparação real/simulado, progresso
   e exportação de um pacote com CSV, máscaras, figuras e manifesto.
4. **Distribuição:** primeiro empacotar o aplicativo local para Debian/Linux
   em formato de pasta, testar em uma máquina limpa e só depois considerar
   executável único e builds para outros sistemas. O XRMC pode permanecer
   como componente opcional enquanto suas bibliotecas nativas forem tratadas.
5. **GitHub:** publicar código, exemplos de configuração e testes. A
   `.gitignore` exclui DICOMs, resultados reais, ambiente virtual, binários
   locais, PDF do TCC e atalho com caminho absoluto. Decidir licença e autoria
   da citação antes da publicação pública. Fornecer dados de demonstração
   sintéticos para que qualquer pessoa consiga executar os testes.

## Estado verificado nesta proposta

- O XRMC atual simula uma placa de PMMA com uma perfuração passante e exporta
  `float64` em `imagem.npy`; `validar_minimo.py` mediu razão de transmissão
  furo/PMMA de 1,853070 na saída existente. Isso verifica esse experimento,
  sem calibrar a simulação contra as imagens Philips.
- Os nove DICOMs locais têm campos de identificação preenchidos e tags
  privadas. Nenhum deles deve entrar automaticamente em um repositório
  público. Uma eventual divulgação de imagens requer revisão específica dos
  metadados e pixels, além de autorização para uso dos dados.
- O diretório `.git` local está vazio; `git status` falha. A integração GitHub
  ainda não está conectada nesta sessão. A publicação precisa de um repositório
  válido, escolha de nome e visibilidade e revisão do conjunto de arquivos.
