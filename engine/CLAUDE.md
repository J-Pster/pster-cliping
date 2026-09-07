# engine

Pipeline Python de geração de clipes. Recebe um vídeo (URL do YouTube ou arquivo local) e
entrega clipes 9:16 e 16:9 legendados, com thumbnail, título, descrição e hashtags.

## Stack

- Python >= 3.11, `pytest`, `ruff`
- ffmpeg/libass no PATH (corte, reenquadramento, burn-in de legenda, encode)
- Transcrição em nuvem (ElevenLabs) por padrão; WhisperX/faster-whisper como opção local
- LLM de texto: Claude ou Gemini via `CLIPADOR_TEXT_LLM_PROVIDER`

## Layout

```
src/clipador/
  ingest/ download/       # resolve a entrada, baixa com yt-dlp
  transcribe/             # etapa 3: transcrição, normalização, vocabulário da KB
  select/                 # etapa 4: seleção de trechos por LLM + rerank + prosódia
  reframe/                # etapa 5: recorte vertical, detecção de rosto e de quem fala
  subtitles/              # etapa 6: geração do .ass e burn-in
  thumbnail/ metadata/    # thumbnail composta e metadados por LLM
  export/                 # corte, marca d'água, thumbnail como 1o frame, fila de revisão
  kb/                     # base de conhecimento por categoria (dossiê + tópicos)
assets/fonts/             # fontes .ttf embarcadas da legenda (versionadas, ver README lá)
kb/<categoria>/           # conteúdo da KB: politico_pessoa, jogos, livro_audiobook
```

## Comandos

```bash
pip install -e ".[video,cloud-transcribe,thumbnail-ai]"
python -m pytest tests/ -q              # suíte offline, nenhum teste chama rede ou ffmpeg real
python -m clipador.cli <input> --category <cat> --watermark on|off
python scripts/run_test_video.py        # ponta a ponta no vídeo de teste, com GPU
python scripts/fetch_fonts.py           # reconstrói assets/fonts/
```

---

# Regras vinculantes

## Transcrição: sempre ElevenLabs Scribe v2

**Toda transcrição usa o Scribe v2 por padrão** (`DEFAULT_BACKEND = "elevenlabs"` em
`transcribe/factory.py`). Isso é decisão medida, não preferência: rodamos o mesmo áudio
nos dois backends e o local produziu **alucinações**, texto inventado que sai
gramaticalmente plausível e seria queimado no clipe.

Evidência completa em `.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md`.
**Não troque esse default sem refazer a medição descrita lá.**

- Exige `ELEVENLABS_API_KEY` no `.env`. Sem ela o pipeline **falha alto**, nunca cai
  calado num backend local: a diferença é de qualidade, e uma queda silenciosa entregaria
  clipe pior sem ninguém perceber.
- Backends locais (`--transcriber whisperx`) existem para áudio que não pode sair da
  máquina ou uso offline. São escolha explícita.
- `no_verbatim` fica **ligado**. Ele converte a pontuação ditada em voz alta ("Ponto:")
  no sinal de verdade, transforma número por extenso em dígito e remove gagueira.

## Transcrição: normalização é obrigatória e roda dentro do transcriber

`transcribe/normalize.py` conserta quatro defeitos que todo ASR produz e que chegavam
intactos na legenda: sigla soletrada (`G .A .E .C .O.` → `GAECO`), pontuação órfã,
duração zero por palavra, e repetição alucinada. Roda dentro de cada `build_result*`, não
no pipeline, para que o `transcription.json` em cache já nasça normalizado.

A normalização **renumera os `word_id`**. Eles são a referência estável da seleção e do
`manifest.json`, então qualquer coisa que junte ou descarte tokens precisa acontecer
antes de qualquer coisa que grave word_id.

## Legenda: o que não desfazer

`subtitles/` foi reconstruído em 2026-09-02. Quatro pontos que parecem detalhe e não são:

1. **`Fontsize` do ASS não é o em da fonte.** O libass converte por
   `unitsPerEm / (usWinAscent + usWinDescent)`, o que dá entre 0.58 e 0.77 nas fontes
   embarcadas. Medir com o em cru superestima a largura do texto em até 42%, o que erra a
   quebra de linha e desloca todo `\pos`. Ver `subtitles/fonts.py::em_scale`, conferido
   contra o render real do libass com erro abaixo de 0.5%.
2. **As fontes são embarcadas em `assets/fonts/` e passadas ao libass via `fontsdir`.**
   Quando a fonte do estilo não existe no fontconfig do sistema, o libass **não falha**:
   cai numa fonte genérica em silêncio e o clipe sai errado sem nada no log.
3. **A quebra de linha é nossa, com `WrapStyle: 2`.** É calculada em pixels medidos na
   fonte real e escrita com `\N`. Deixar o libass quebrar sozinho fazia o bloco de
   legenda mudar de altura a cada cue.
4. **O tamanho da fonte é fração da altura do quadro, resolvido por formato** em
   `subtitles/presets.py`. Guardar em pixel foi o que produziu o bug de o mesmo `72`
   valer 3,75% da altura no 9:16 e 6,7% no 16:9, ou seja a legenda do vertical, que é a
   que mais precisa ser grande, era proporcionalmente quase metade da do horizontal.

---

## O engine é caixa-preta para o backend

O backend NestJS orquestra e persiste. Ele não reimplementa em TypeScript nada que viva
aqui (transcrição, cortes, legendas, thumbnails).

## Convenções locais

- Todo componente pesado é injetável; o default só é construído quando nada foi passado.
  É por isso que a suíte inteira roda offline, sem GPU e sem ffmpeg real.
- Comentário no código explica **por que**, não o que. Vários deles registram um erro já
  cometido (aspas no filtro `ass=` do ffmpeg no Windows, `\fscx` comendo o espaço entre
  palavras, log de backend de nuvem imprimindo `large-v3 (cuda/float16)`). Não apague
  esses comentários ao refatorar: eles são a memória do bug.
- Sem em dash em nada, nem em código, nem em docs, nem em texto de UI.
