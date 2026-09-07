# Sobre o canal

Livros geralmente de nao-ficcao (politica, estrategia, negocios, tecnico,
ensaio), nao romance. Preencha este arquivo (e outros em
`kb/livro_audiobook/core/`) com fatos verificaveis especificos do canal:
titulo e autor do(s) livro(s) narrado(s), nome do narrador, tom de voz
tipico da leitura, e qualquer regra de sensibilidade (ex.: ressalvas do
autor que nao podem ser citadas fora do paragrafo que as contextualiza).

Este dossie e opcional: com este arquivo vazio ou ausente, a selecao de
cortes e a geracao de metadados/thumbnail da categoria "livro_audiobook"
funcionam normalmente usando so as instrucoes fixas do prompt (ver
`clipador.select.selector.SELECTION_INSTRUCTIONS_BY_CATEGORY`), sem citar
nenhum elemento de dossie.

Arquivos de topico especificos (ex.: glossario de conceitos-chave, resumo
de capitulos, frameworks citados pelo autor) vao em
`kb/livro_audiobook/topics/`, no mesmo formato dos arquivos de
`kb/politico_pessoa/topics/`.
