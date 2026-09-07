# Transcrição: ElevenLabs Scribe v2 vira o backend padrão

**Data:** 2026-09-02
**Status:** vigente
**Escopo:** `engine/src/clipador/transcribe/`
**Decisão:** o backend padrão de transcrição do pipeline passa de **WhisperX local** para
**ElevenLabs Scribe v2** (`DEFAULT_BACKEND = "elevenlabs"` em `transcribe/factory.py`).

---

## Regra operacional

**Toda transcrição do pipeline usa o ElevenLabs Scribe v2 por padrão.** Não troque esse
default de volta sem refazer a medição descrita abaixo.

Os backends locais continuam existindo e funcionando, mas são escolha explícita:

| Backend | Quando usar |
| --- | --- |
| `elevenlabs` (Scribe v2) | **Padrão.** Todo uso normal. |
| `assemblyai` | Segunda opção de nuvem. Preço parecido, alinhamento próprio. |
| `whisperx` | Áudio que não pode sair da máquina, ou sem internet. Qualidade menor. |
| `faster-whisper` | Último recurso. Timestamp por palavra erra 200-300ms. |

Sem `ELEVENLABS_API_KEY` configurada, o pipeline **falha alto** (`TranscriberConfigError`)
em vez de cair calado num backend local. A diferença entre nuvem e local aqui é de
qualidade medida, não de conveniência: uma queda silenciosa entregaria clipe pior sem
ninguém perceber, que é exatamente o modo de falha que este projeto evita.

---

## Como a decisão foi tomada

Não por reputação de fornecedor nem por benchmark publicado. Rodamos o **mesmo áudio**
nos dois backends e comparamos as saídas palavra a palavra.

**Corpus:** `-SlNLan6jp0.mp4`, 11min18s, leitura em PT-BR do capítulo "Prendeu, Matou" do
Livro Amarelo. Áudio de estúdio, um locutor, registro formal.

**Referência de grafia:** o glossário da própria KB
(`engine/kb/politico_pessoa/core/20-glossario.md` e `topics/02-seguranca-publica.md`), que
fixa a grafia correta dos termos de domínio do capítulo.

**Baseline local:** WhisperX `medium` com alinhamento CTC, que era a configuração que
gerava os clipes até então.

### Resultado

Concordância palavra a palavra: **94,8%**. Nas 44 divergências:

- **Scribe claramente certo: ~24**
- **Local claramente certo: 1** (`banimento judicial`, grafia do glossário, que o Scribe
  trocou por `jurisdicional`)
- Resto: neutro (artigos, `Esse`/`Este`, `receitas`/`receita`)

Termos de domínio conferidos contra o glossário, dos 20 que aparecem no trecho:
**local 17, Scribe 19.**

### Os dois casos que decidiram

Não são erros de grafia. São **alucinações do backend local**, que é o tipo perigoso: o
texto sai gramaticalmente plausível e seria queimado no clipe sem ninguém notar.

```
LOCAL : ...pois hoje não temos a condição de revertir o crime, mas a
        capacidade institucional de resposta a essas organizações...
SCRIBE: ...pois hoje não temos a capacidade institucional de resposta
        a essas organizações...
```

A frase do local não fecha. E esse é exatamente o trecho onde a transcrição local tinha
**seis palavras colapsadas no mesmo timestamp (151,72s)**, assinatura clássica de
alinhador falhando sobre texto inventado.

```
LOCAL : ...para os crimes que mais podem acontecer. O que mais
        aterroriza um brasileiro comum? Sobretudo...
SCRIBE: ...para os crimes que mais aterrorizam o brasileiro comum.
        Sobretudo...
```

```
LOCAL : ...Soluções e propostas Soluções e propostas O texto surgiu o lema E dá título...
SCRIBE: ...Nesse contexto, ... o lema "Prendeu, matou", entre aspas, que dá título...
```

O local repetiu o cabeçalho da seção e engoliu a frase entre aspas, que é o lema do
capítulo.

### Erros de termo, medidos contra o glossário

| Termo de referência | Local | Scribe |
| --- | --- | --- |
| `narcoestado` | `narco -estado` | correto |
| `lei antifacção` | `anti -facção` | correto |
| `última ratio` (termo jurídico) | **`última Rachel`** | correto (sem o acento em "ultima") |
| `Garantia da Lei e da Ordem, GLO` | `Garantia da Lei da Ordem`, sem o "e" e sem a sigla | correto |
| `CECOT` (prisão salvadorenha) | `Secot` | correto |
| `sucessivos` | `suscetivos` | correto |
| `critérios` | `critórios` | correto |
| `neutralizá-los` | `neutralizados` | correto |
| `DPI` | ausente | correto |
| `banimento judicial` | **correto** | `jurisdicional` |

Mais os hífens que o local quebrava sistematicamente e o Scribe acerta: `pós-1988`,
`soma-se`, `mantém-se`, `sustentando-se`, `filiar-se`.

---

## `no_verbatim=True`, e por que ele fica ligado

Descoberto rodando, não lendo documentação. A primeira passada com o Scribe tinha duas
fraquezas: número por extenso (`vinte por cento`) e tokens de gagueira (`que-a`, `f-a`,
`No--`). O parâmetro `no_verbatim` da API resolve os dois **e mais um problema que o
backend local não resolvia**: o locutor dita a pontuação em voz alta ao ler uma lista, e
a palavra "Ponto" era queimada na legenda.

```
                        local   verbatim  no_verbatim
palavras                 1319      1317         1287
"Ponto" ditado              3         9            0
tokens com digito           4         3            6
gagueira (xx-yy / --)       0         5            0
```

Também: `preventida-prevent-preventivas` → `preventivas`, `enfaceLamento` →
`enfraquecimento`.

**Custo aceito:** a caixa de nome próprio composto se perde (`Direito Penal` vira
`direito penal`). Invisível nos presets de legenda em caixa alta, perda pequena no preset
`classico` e no prompt de seleção.

---

## Custo e desempenho

| | Local (WhisperX) | Scribe v2 |
| --- | --- | --- |
| Tempo (vídeo de 11min18s) | dezenas de minutos, ocupando a GPU | **23,8s** (9,5s de extração + 12s de API) |
| VRAM | ~3 GB, mais alinhador e pyannote | zero |
| Custo | zero em dinheiro | **$0.22/hora de áudio** (~4 centavos por esse vídeo) |
| Diarização | pyannote, exige token do HuggingFace e aceite de termos | inclusa, sem configuração |

Vinte vídeos de 1h por mês custam cerca de **$4.40**. O ganho maior não é o dinheiro: é
liberar a GPU, que no mesmo pipeline é disputada pelo NVENC, pelo MediaPipe e pelo
recorte de thumbnail.

---

## Limites conhecidos desta medição

Registrados para quem for revisitar a decisão:

1. **Uma amostra, um tipo de conteúdo.** Áudio de estúdio, um locutor, leitura de texto
   formal. É o caso mais fácil que existe. Debate com sobreposição de fala pode ranquear
   diferente, principalmente na diarização.
2. **O baseline local era `medium`, não `large-v3`.** É a comparação contra o que gerava
   os clipes de fato, mas não contra o local no melhor dele. Erros como `Rachel` por
   `ratio` e `Secot` por `CECOT` são o tipo de coisa que o `large-v3` tende a acertar
   mais. O default local foi elevado para `large-v3` na mesma sessão, sem nova medição.
3. **Sem ground truth.** Não existe transcrição de referência do áudio, então não há WER.
   O que foi medido é concordância entre as duas saídas mais acerto de termo contra o
   glossário da KB.
4. **O áudio sai da máquina.** Decisão editorial, não técnica, registrada aqui porque o
   conteúdo é político.

## Como refazer a medição

```bash
cd engine
# Scribe (default)
python scripts/run_test_video.py
# Local, mesmo vídeo, para comparar
CLIPADOR_TRANSCRIBER=whisperx python scripts/run_test_video.py
```

As transcrições ficam em `.clipador/<video_id>/transcription.json`. Apague o arquivo entre
as duas rodadas, senão a segunda reaproveita o cache da primeira.

## Consequências

- `ELEVENLABS_API_KEY` no `.env` do engine deixa de ser opcional para o uso padrão.
- `pip install -e ".[cloud-transcribe]"` passa a ser parte da instalação normal.
- `SCHEMA_VERSION` da transcrição está em 2. Cache de schema antigo é descartado e o
  vídeo é retranscrito; como os `word_id` mudam, o `manifest.json` daquela pasta de saída
  fica obsoleto para "gerar mais" naquele vídeo específico.
