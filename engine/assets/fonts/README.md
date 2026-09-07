# Fontes embarcadas da legenda

Arquivos usados pelo burn-in de legenda (`clipador.subtitles`). O diretorio inteiro e
repassado ao libass pela opcao `fontsdir` do filtro `ass` do ffmpeg.

**Por que ficam versionados aqui:** o libass resolve o campo `Fontname` do estilo ASS no
fontconfig do sistema. Quando a fonte nao existe ali, ele nao falha - cai numa fonte
generica em silencio, e o clipe sai com a legenda errada sem nada no log. Embarcar o
`.ttf` faz o mesmo arquivo valer em qualquer maquina, no CI e no container.

Para reconstruir o diretorio: `python scripts/fetch_fonts.py` (a partir de `engine/`).

| Arquivo | `Fontname` no ASS | Preset | Origem |
| --- | --- | --- | --- |
| `Montserrat-ExtraBold.ttf` | `Montserrat ExtraBold` | `impacto`, `classico` | [JulietaUla/Montserrat](https://github.com/JulietaUla/Montserrat) |
| `Anton-Regular.ttf` | `Anton` | `anton` | [google/fonts](https://github.com/google/fonts/tree/main/ofl/anton) |
| `ArchivoBlack-Regular.ttf` | `Archivo Black` | `neon` | [google/fonts](https://github.com/google/fonts/tree/main/ofl/archivoblack) |
| `BebasNeue-Regular.ttf` | `Bebas Neue` | (disponivel, sem preset) | [google/fonts](https://github.com/google/fonts/tree/main/ofl/bebasneue) |

O `Fontname` nao e o nome do arquivo: o libass casa pela tabela `name` do TTF. Montserrat
e o unico caso em que familia (`Montserrat`) e peso (`ExtraBold`) sao campos separados,
por isso o valor usado e o fullname. As outras tres sao familias de peso unico.

## Licenca

Todas sob **SIL Open Font License 1.1**, que permite uso comercial, redistribuicao e
embutir no produto. O texto da licenca acompanha cada projeto de origem, nos links acima.
