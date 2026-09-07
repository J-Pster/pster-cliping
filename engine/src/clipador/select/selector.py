"""Selecao de trechos por LLM: dossie da KB + transcricao com word_ids, saida estruturada por tool use."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from clipador import category as category_module
from clipador.kb.knowledge import KnowledgeBase
from clipador.llm.provider import MODEL_ID, get_client
from clipador.select.models import (
    CLIP_FORMATS,
    LONG_FORMAT,
    LONG_MAX_SECONDS,
    LONG_MIN_SECONDS,
    MAX_SCORE,
    MIN_SCORE,
    SHORT_FORMAT,
    SHORT_MAX_SECONDS,
    SHORT_MIN_SECONDS,
    ClipCandidate,
)
from clipador.select.silence import DEFAULT_SILENCE_GAP, expand_to_min_duration, snap_to_silence
from clipador.transcribe.models import TranscriptionResult

TOOL_NAME = "propose_clips"

SELECTION_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Registra os trechos escolhidos como candidatos a clipe. Cada candidato referencia "
        "ids de palavras que existem na transcricao fornecida, nunca timestamps inventados."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "description": "Candidatos ordenados do melhor para o pior.",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_word_id": {
                            "type": "integer",
                            "description": "Id da primeira palavra do trecho.",
                        },
                        "end_word_id": {
                            "type": "integer",
                            "description": "Id da ultima palavra do trecho.",
                        },
                        "format": {
                            "type": "string",
                            "enum": list(CLIP_FORMATS),
                            "description": (
                                f"'{SHORT_FORMAT}' para vertical de 60s a 90s, "
                                f"'{LONG_FORMAT}' para horizontal de 8 a 12 minutos "
                                "(nunca proponha long_16x9 com menos de 8 minutos)."
                            ),
                        },
                        "score": {
                            "type": "integer",
                            "description": "Potencial de viralizacao de 0 a 99.",
                        },
                        "justificativa": {
                            "type": "string",
                            "description": (
                                "Por que este trecho funciona, citando um elemento verificavel "
                                "do dossie (pauta, termo do glossario, traco de voz) quando couber."
                            ),
                        },
                    },
                    "required": [
                        "start_word_id",
                        "end_word_id",
                        "format",
                        "score",
                        "justificativa",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    },
}

_POLITICS_PERSON_SELECTION_INSTRUCTIONS = f"""Voce seleciona trechos de video de um movimento politico para virarem clipes.

Os dois formatos pedem coisas DIFERENTES um do outro, nao aplique o mesmo criterio nos dois:

## {SHORT_FORMAT} (vertical, 60-90s, feed/Reels/Shorts)
E uma peca autonoma: a pessoa que assiste NUNCA viu o resto do video. Duracao
minima de 60s: se o gancho perfeito renderia so 20-30s, ESTENDA o trecho
(mais contexto antes, mais desenvolvimento do argumento depois) ate fechar
pelo menos 60s em vez de entregar um clipe curto demais.
1. Abre JA na acao, literalmente a primeira palavra do trecho precisa comecar
   no meio de uma frase com carga (afirmacao forte, numero, provocacao), nunca
   numa saudacao, num "entao" de transicao ou numa frase que so faz sentido
   depois de uma pergunta que ficou fora do corte.
2. Autocontido de verdade: banido comecar com pronome/referencia sem
   antecedente dentro do proprio trecho ("isso", "ele", "essa proposta", "por
   isso"), se a primeira frase depende de algo dito ANTES do word_id inicial,
   mova o inicio pra tras ate incluir o antecedente, ou descarte o trecho.
3. Tem uma virada/payoff antes do fim, o trecho nao pode terminar largado no
   meio de um raciocínio; a ultima frase fecha uma ideia (conclusao, dado
   concreto, frase de efeito), nao um "e tambem..." cortado.
4. Carga emocional ou tensao que prenda do primeiro ao ultimo segundo.
5. Alinhamento com as pautas prioritarias e o tom de voz do dossie abaixo.

## {LONG_FORMAT} (16:9, 8-12min, ALVO 10min, "melhores momentos" pra YouTube)
Duracao e requisito duro, nao sugestao: o intervalo tem que cobrir entre 8 e
12 minutos, e o ALVO e 10 minutos, 8 minutos e o PISO MINIMO ACEITAVEL, nao a meta.
NAO pare de expandir so porque ja passou de 8 minutos: continue puxando contexto
do mesmo assunto (mais desenvolvimento do argumento, mais contraponto, mais exemplo)
ate chegar perto de 10 minutos, e so aceite ficar mais perto do piso de 8 minutos se
o arco do assunto genuinamente se esgotar ali (continuar geraria conteudo fora do
tema ou repetitivo, nao substancia nova de verdade). NUNCA proponha um long_16x9 do
tamanho de um clipe curto (menos de 8 minutos) so porque o melhor momento isolado ali
e curto, nesse caso, EXPANDA a janela puxando contexto do mesmo assunto antes e/ou
depois daquele momento ate fechar pelo menos 8 minutos continuos e coerentes (o ideal
continua sendo chegar perto de 10). Um clipe longo
usa um metodo DIFERENTE do curto, nao e a mesma logica aplicada a um
intervalo maior, e um resumo editado, nao um unico gancho: pode reunir mais
de uma ideia do mesmo tema, contanto que sejam do MESMO trecho continuo (voce
so pode apontar um unico intervalo start/end por candidato, sem pular partes
no meio).
1. Arco com comeco-meio-fim dentro do proprio intervalo: apresenta o tema,
   desenvolve o argumento, fecha com uma conclusao, nao e so "o momento mais
   emocionante" isolado, e a passagem que conta a historia completa daquele
   assunto.
2. Progressao logica perceptivel, cada frase deve levar a proxima, sem saltos
   de assunto abruptos dentro do trecho escolhido.
3. Mais rico e informativo que o formato curto: inclua contexto, explicacao,
   contraponto, repeticao com variacao, substancia suficiente pra alguem
   assistir o video inteiro no YouTube, nao so o clipe mais chocante isolado.
4. Alinhamento com as pautas prioritarias e o tom de voz do dossie abaixo.

Regras inegociaveis (valem pros dois formatos):
- Antes de finalizar CADA candidato, calcule a duracao real: cada segmento na
  transcricao mostra `SSs-SSs` no cabecalho (`## Segmento N | inicio-fim`). Subtraia
  o inicio do segmento da sua primeira palavra do fim do segmento da sua ultima
  palavra e confira que o resultado cai na janela do formato (60-90s curto, 8-12min
  longo) ANTES de responder, nao adivinhe pelo numero de palavras.
- Escolha apenas ids de palavras que aparecem na transcricao enviada; nunca invente numero.
- O trecho precisa comecar e terminar em fronteira de frase, nunca no meio de uma ideia.
- Nao selecione trecho que mude o sentido da fala original quando tirado de contexto.
- Evite temas marcados como sensiveis no dossie, salvo quando o proprio trecho ja traz a nuance.
- Na justificativa, diga explicitamente por que o trecho funciona sozinho pra quem
  nao viu o resto do video (ou, no caso do formato longo, por que o arco se sustenta).

Responda exclusivamente chamando a ferramenta propose_clips."""

_GAMING_SELECTION_INSTRUCTIONS = f"""Voce seleciona trechos de uma gravacao de gameplay (jogo em video) para virarem clipes.

Os dois formatos pedem coisas DIFERENTES um do outro, nao aplique o mesmo criterio nos dois:

## {SHORT_FORMAT} (vertical, 60-90s, feed/Reels/Shorts)
E uma peca autonoma: a pessoa que assiste NUNCA viu o resto do video. Duracao
minima de 60s: se o highlight perfeito renderia so 20-30s, ESTENDA o trecho
(mais setup antes da jogada, mais reacao/comemoracao depois) ate fechar pelo
menos 60s em vez de entregar um clipe curto demais.
1. Abre JA perto da acao, comeca no setup imediato de UM highlight forte
   (eliminacao, jogada decisiva, clutch, susto, momento comico, virada de
   partida), nunca numa fala de transicao neutra ("beleza, vamo la", tela de
   carregamento, menu).
2. O highlight PRECISA acontecer dentro do proprio trecho, nunca corte
   deixando a eliminacao/jogada/resultado subentendido fora do intervalo; o
   pico de acao (e a reacao do jogador a ele) tem que estar audivel dentro do
   corte.
3. Fecha na reacao/consequencia do highlight (comemoracao, xingamento, risada,
   resultado da partida), nao larga no meio da jogada seguinte.
4. Use os sinais de prosodia (energia/pitch/ritmo) como indicio de onde a
   reacao do jogador e mais forte, pico de energia e pitch normalmente marca
   o instante exato do highlight, mesmo sem HUD/kill-feed visivel na
   transcricao.
5. Um unico highlight por clipe curto, nao tente encaixar duas jogadas
   diferentes, prefira o momento mais intenso.

## {LONG_FORMAT} (16:9, 8-12min, ALVO 10min, "melhores momentos" da sessao)
Duracao e requisito duro, nao sugestao: o intervalo tem que cobrir entre 8 e
12 minutos, e o ALVO e 10 minutos, 8 minutos e o PISO MINIMO ACEITAVEL, nao a
meta. Diferente do curto, aqui voce pode reunir MULTIPLOS highlights da mesma
sessao (2 a 5 momentos fortes), desde que estejam dentro do MESMO intervalo
continuo (um unico start/end por candidato, sem pular partes no meio).
1. Estrutura em ordem CRESCENTE de intensidade: comeca com um highlight
   solido pra prender, desenvolve com mais jogadas no meio, termina no
   momento mais forte da sessao (a melhor eliminacao, a vitoria, a virada mais
   dramatica), nunca termina num momento fraco so porque bateu o tempo.
2. Cada highlight dentro do intervalo precisa ter setup-acao-reacao proprios,
   nao e so uma sequencia de jogadas soltas coladas.
3. Comentario/narracao do jogador entre os highlights e bem-vindo (contexto,
   estrategia, reacao), desde que mantenha ritmo.
4. Alinhamento com o tom/estilo de jogo do dossie abaixo, quando houver.

Regras inegociaveis (valem pros dois formatos):
- Antes de finalizar CADA candidato, calcule a duracao real: cada segmento na
  transcricao mostra `SSs-SSs` no cabecalho (`## Segmento N | inicio-fim`). Subtraia
  o inicio do segmento da sua primeira palavra do fim do segmento da sua ultima
  palavra e confira que o resultado cai na janela do formato (60-90s curto, 8-12min
  longo) ANTES de responder, nao adivinhe pelo numero de palavras.
- Escolha apenas ids de palavras que aparecem na transcricao enviada; nunca invente numero.
- O trecho precisa comecar e terminar em fronteira de frase (ou pausa natural), nunca no
  meio de uma jogada em andamento.
- Diferente de outras categorias, um pedacinho do FIM de um trecho ja usado pode
  aparecer como INICIO de um novo trecho (ex.: reaproveitar o rebote de uma jogada
  como gancho da proxima), o que nao pode e o MESMO highlight virar dois clipes
  praticamente identicos; o conteudo central de cada clipe tem que ser um highlight
  DIFERENTE do highlight central dos trechos ja usados.
- Na justificativa, nomeie o tipo de highlight (eliminacao, clutch, virada, momento
  comico etc.) e por que o corte funciona sozinho pra quem nao viu o resto da sessao.

Responda exclusivamente chamando a ferramenta propose_clips."""

_BOOK_AUDIOBOOK_SELECTION_INSTRUCTIONS = f"""Voce seleciona trechos de uma narracao/leitura de livro (audiobook) para virarem clipes.

O livro normalmente e de nao-ficcao (politica, estrategia, negocios, tecnico,
ensaio), nao um romance: trate "virada" como virada de RACIOCINIO (um
argumento que muda a conclusao, um dado que reformula o problema, uma tese
contraintuitiva), nunca como virada de enredo ou de personagem.

Os dois formatos pedem coisas DIFERENTES um do outro, nao aplique o mesmo criterio nos dois:

## {SHORT_FORMAT} (vertical, 60-90s, feed/Reels/Shorts)
E uma peca autonoma: quem assiste/ouve NUNCA ouviu o resto do livro. Duracao
minima de 60s: se o trecho perfeito renderia so 20-30s, ESTENDA (mais contexto
do argumento antes, mais desenvolvimento do raciocinio depois) ate fechar
pelo menos 60s em vez de entregar um clipe curto demais.
1. Abre JA com carga, a primeira frase do trecho precisa ter peso proprio
   (uma afirmacao forte, um dado surpreendente, uma tese contraintuitiva do
   autor), nunca uma frase de transicao neutra de narrador ("capitulo quatro",
   "continuando de onde paramos").
2. Autocontido de verdade: banido comecar com pronome/referencia sem
   antecedente dentro do proprio trecho ("isso", "ele", "essa ideia"), se a
   primeira frase depende de algo dito ANTES do word_id inicial, mova o
   inicio pra tras ate incluir o antecedente, ou descarte o trecho.
3. Fecha numa virada/payoff real de raciocinio: conclusao forte, dado
   concreto, argumento que fecha a ideia, nunca larga no meio de um
   raciocinio ou descricao neutra.
4. Use os sinais de prosodia (energia/pitch/ritmo) como indicio de enfase do
   narrador, mudanca de ritmo (desacelera antes de uma conclusao, acelera em
   argumento) e pico de pitch normalmente marcam a frase mais forte do trecho.
5. Carga intelectual/argumentativa que prenda do primeiro ao ultimo segundo.

## {LONG_FORMAT} (16:9, 8-12min, ALVO 10min, capitulo ou arco de argumento completo)
Duracao e requisito duro, nao sugestao: o intervalo tem que cobrir entre 8 e
12 minutos, e o ALVO e 10 minutos, 8 minutos e o PISO MINIMO ACEITAVEL, nao a
meta. NAO pare de expandir so porque ja passou de 8 minutos: continue puxando
contexto do mesmo capitulo/argumento ate chegar perto de 10 minutos, e so
aceite ficar mais perto do piso de 8 minutos se o capitulo/argumento
genuinamente se encerrar ali. NUNCA proponha um long_16x9 do tamanho de um
clipe curto so porque o momento mais forte ali e curto, EXPANDA a janela
puxando contexto do mesmo capitulo/argumento antes e/ou depois daquele momento.
1. Arco com comeco-meio-fim dentro do proprio intervalo: um capitulo ou secao
   inteira, com tese, desenvolvimento do argumento e conclusao, nao e so "o
   trecho mais forte" isolado, e a passagem que conta o argumento completo.
2. Progressao logica perceptivel, cada frase leva a proxima, sem saltos de
   assunto abruptos dentro do trecho escolhido.
3. Mais rico que o formato curto: inclua contexto, exemplos, contraponto,
   desenvolvimento do argumento, substancia suficiente pra alguem acompanhar
   o audiobook completo depois, nao so o trecho mais impactante isolado.
4. Alinhamento com o tom de narracao e o estilo do livro do dossie abaixo,
   quando houver.

Regras inegociaveis (valem pros dois formatos):
- Antes de finalizar CADA candidato, calcule a duracao real: cada segmento na
  transcricao mostra `SSs-SSs` no cabecalho (`## Segmento N | inicio-fim`). Subtraia
  o inicio do segmento da sua primeira palavra do fim do segmento da sua ultima
  palavra e confira que o resultado cai na janela do formato (60-90s curto, 8-12min
  longo) ANTES de responder, nao adivinhe pelo numero de palavras.
- Escolha apenas ids de palavras que aparecem na transcricao enviada; nunca invente numero.
- O trecho precisa comecar e terminar em fronteira de frase, nunca no meio de uma ideia.
- PROIBIDO qualquer sobreposicao com um trecho ja usado, mesmo parcial (ao contrario
  de outras categorias, aqui nao vale reaproveitar nem um pedacinho de um trecho
  anterior), cada clipe cobre uma passagem exclusiva do livro, pra nao repetir
  conteudo pra quem acompanha a serie inteira.
- Nao selecione trecho que mude o sentido do argumento original quando tirado de
  contexto (ex.: uma ressalva do autor lida fora do paragrafo que a contextualiza).
- Na justificativa, diga explicitamente por que o trecho funciona sozinho pra quem
  nao ouviu o resto do livro (ou, no formato longo, por que o capitulo/secao se
  sustenta sozinho).

Responda exclusivamente chamando a ferramenta propose_clips."""

SELECTION_INSTRUCTIONS_BY_CATEGORY: dict[str, str] = {
    category_module.POLITICS_PERSON: _POLITICS_PERSON_SELECTION_INSTRUCTIONS,
    category_module.GAMING: _GAMING_SELECTION_INSTRUCTIONS,
    category_module.BOOK_AUDIOBOOK: _BOOK_AUDIOBOOK_SELECTION_INSTRUCTIONS,
}

# Mantido para quem ainda importa o nome antigo diretamente: sempre a variante politico/pessoa.
SELECTION_INSTRUCTIONS = _POLITICS_PERSON_SELECTION_INSTRUCTIONS

# Tolerancia de sobreposicao (em palavras) entre um candidato novo e um trecho ja usado
# NO MESMO formato. Zero pra todas as categorias exceto jogos: la um pedacinho do fim de
# um clipe pode virar o gancho do proximo (ver regra na instrucao de selecao acima).
GAMING_OVERLAP_TOLERANCE_WORDS = 40

_OVERLAP_TOLERANCE_WORDS_BY_CATEGORY: dict[str, int] = {
    category_module.GAMING: GAMING_OVERLAP_TOLERANCE_WORDS,
}


def overlap_tolerance_words(category: str) -> int:
    return _OVERLAP_TOLERANCE_WORDS_BY_CATEGORY.get(category, 0)


PROSODY_HEADER = """Sinais de prosodia medidos direto no audio, nao e transcricao.
Cada linha cobre uma janela de tempo: energia RMS media, desvio do pitch medio da janela em
relacao ao desvio-padrao do video inteiro (positivo = voz mais aguda que o normal, sinal de
enfase ou ativacao emocional) e ritmo de fala em palavras por segundo.
Use como indicio de onde a fala pega; a decisao final ainda sai do conteudo da transcricao."""


def _attr(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def build_transcript_view(transcription: TranscriptionResult) -> str:
    """Serializa a transcricao expondo o word_id de cada palavra, que e a referencia do corte."""
    blocks: list[str] = []
    for segment in transcription.segments:
        if not segment.words:
            continue
        speaker = segment.speaker or "desconhecido"
        header = f"## Segmento {segment.id} | {segment.start:.2f}s-{segment.end:.2f}s | fala: {speaker}"
        body = " ".join(f"[{word.id}] {word.text}" for word in segment.words)
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks)


def build_system_blocks(
    kb: KnowledgeBase, category: str = category_module.DEFAULT_CATEGORY
) -> list[dict[str, Any]]:
    """Prefixo estavel do prompt: instrucoes (por categoria) + dossie, com o cache marcado
    no ultimo bloco."""
    instructions = SELECTION_INSTRUCTIONS_BY_CATEGORY[category_module.validate_category(category)]
    blocks: list[dict[str, Any]] = [{"type": "text", "text": instructions}]
    dossier = kb.dossier()
    if dossier:
        blocks.append({"type": "text", "text": dossier})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def build_used_ranges_block(used_ranges: Mapping[str, Sequence[tuple[int, int]]] | None) -> str:
    """Lista os trechos ja usados por formato pra o LLM evitar propor de novo (dedup
    e SO dentro do mesmo formato - o mesmo assunto pode virar um curto E um longo)."""
    if not used_ranges:
        return ""
    lines = [
        f"- {clip_format}: " + ", ".join(f"{start}-{end}" for start, end in ranges)
        for clip_format, ranges in used_ranges.items()
        if ranges
    ]
    if not lines:
        return ""
    return (
        "Trechos (word_id) JA USADOS em rodadas anteriores - nao pode propor de novo o "
        "MESMO intervalo NO MESMO formato listado (reaproveitar o mesmo assunto em "
        "formato diferente do listado esta liberado):\n" + "\n".join(lines) + "\n\n"
    )


def build_user_prompt(
    transcription: TranscriptionResult,
    max_candidates: int,
    prosody_table: str | None = None,
    used_ranges: Mapping[str, Sequence[tuple[int, int]]] | None = None,
) -> str:
    words = transcription.words
    id_range = f"{words[0].id} a {words[-1].id}" if words else "vazio"
    prosody_block = f"{PROSODY_HEADER}\n\n{prosody_table}\n\n" if prosody_table else ""
    used_block = build_used_ranges_block(used_ranges)
    return (
        f"{prosody_block}{used_block}"
        f"Transcricao com timestamp por palavra (ids validos: {id_range}).\n\n"
        f"{build_transcript_view(transcription)}\n\n"
        f"Aponte no maximo {max_candidates} candidatos a clipe, misturando "
        f"{SHORT_FORMAT} e {LONG_FORMAT} quando o material permitir."
    )


# Tolerancia percentual em cima dos limites de select/models.py: o alvo (60-90s curto,
# 8-12min longo) e o que o prompt pede, mas o corte real nao precisa bater exato - um
# candidato otimo que fecha em 110s (curto) e melhor que descartar. Mais generoso pra
# cima que pra baixo: passar um pouco do teto e normal (arredondar pro proximo corte de
# silencio natural), ficar bem abaixo do piso normalmente significa que o trecho e curto
# demais de verdade pro formato.
LOWER_TOLERANCE_RATIO = 0.25
UPPER_TOLERANCE_RATIO = 0.30

_DURATION_BOUNDS_SECONDS = {
    SHORT_FORMAT: (SHORT_MIN_SECONDS, SHORT_MAX_SECONDS),
    LONG_FORMAT: (LONG_MIN_SECONDS, LONG_MAX_SECONDS),
}

# O formato longo tem piso RIGIDO (pedido explicito do usuario: "nunca menos de 8
# minutos"), sem a tolerancia pra baixo que o curto tem - por isso zera o lado "menor"
# so pro longo (o lado "maior" continua com a mesma folga, passar um pouco do teto e
# normal pros dois formatos).
_TOLERANCE_RATIOS_BY_FORMAT = {
    SHORT_FORMAT: (LOWER_TOLERANCE_RATIO, UPPER_TOLERANCE_RATIO),
    LONG_FORMAT: (0.0, UPPER_TOLERANCE_RATIO),
}


def duration_tolerance_window(clip_format: str) -> tuple[float, float]:
    """Janela flexivel de duracao aceita pro formato: +-% em cima do alvo rigido de
    `_DURATION_BOUNDS_SECONDS` (ver `_TOLERANCE_RATIOS_BY_FORMAT`), pra nao descartar um
    candidato otimo so por passar um pouco do alvo. O piso do formato longo nao tem
    tolerancia pra baixo (fica igual a `LONG_MIN_SECONDS`), os demais lados usam a
    tolerancia percentual normal."""
    min_seconds, max_seconds = _DURATION_BOUNDS_SECONDS[clip_format]
    lower_ratio, upper_ratio = _TOLERANCE_RATIOS_BY_FORMAT[clip_format]
    return min_seconds * (1 - lower_ratio), max_seconds * (1 + upper_ratio)


def validate_candidates(
    raw_candidates: Sequence[Any],
    transcription: TranscriptionResult,
    snap: bool = True,
    silence_threshold: float = DEFAULT_SILENCE_GAP,
    enforce_duration_bounds: bool = False,
) -> list[ClipCandidate]:
    """Descarta o que o LLM alucinou: ids fora do range, ordem invertida, formato desconhecido
    e, com `enforce_duration_bounds=True`, duracao real fora da janela do formato declarado
    (rede de seguranca contra o LLM ignorar o limite do prompt, ex.: rotular um clipe de
    1:30 como long_16x9 quando o formato longo exige 8-12min)."""
    words = transcription.words
    if not words:
        return []

    valid_ids = {word.id for word in words}
    candidates: list[ClipCandidate] = []
    for raw in raw_candidates:
        start_id = _as_int(_attr(raw, "start_word_id"))
        end_id = _as_int(_attr(raw, "end_word_id"))
        if start_id is None or end_id is None:
            continue
        if start_id not in valid_ids or end_id not in valid_ids or start_id > end_id:
            continue

        clip_format = _attr(raw, "format")
        if clip_format not in CLIP_FORMATS:
            continue

        if snap:
            start_id, end_id = snap_to_silence(transcription, start_id, end_id, silence_threshold)

        start_time = transcription.word_by_id(start_id).start
        end_time = transcription.word_by_id(end_id).end

        if enforce_duration_bounds:
            min_seconds, max_seconds = _DURATION_BOUNDS_SECONDS[clip_format]
            lower_bound, upper_bound = duration_tolerance_window(clip_format)
            duration = end_time - start_time
            # O LLM erra a duracao com frequencia (nao "conta" segundos de verdade, so
            # estima pelo texto) - em vez de descartar de cara um trecho curto demais,
            # tenta completar puxando contexto vizinho ate o alvo do formato antes de
            # desistir. So repara pra baixo do piso flexivel: acima do teto so descarta
            # mesmo, cortar um trecho que o LLM escolheu de proposito seria pior que
            # perde-lo.
            if duration < lower_bound:
                repaired = expand_to_min_duration(
                    transcription, start_id, end_id, min_seconds, upper_bound, silence_threshold
                )
                if repaired is None:
                    continue
                start_id, end_id = repaired
                start_time = transcription.word_by_id(start_id).start
                end_time = transcription.word_by_id(end_id).end
                duration = end_time - start_time

            if not (lower_bound <= duration <= upper_bound):
                continue

        score = _as_int(_attr(raw, "score")) or MIN_SCORE
        candidates.append(
            ClipCandidate(
                start_word_id=start_id,
                end_word_id=end_id,
                format=clip_format,
                score=max(MIN_SCORE, min(MAX_SCORE, score)),
                justificativa=str(_attr(raw, "justificativa", "")),
                start=start_time,
                end=end_time,
            )
        )
    return candidates


def _request_candidates(
    transcription: TranscriptionResult,
    kb: KnowledgeBase,
    client: Any | None,
    max_candidates: int,
    model: str,
    max_tokens: int,
    prosody_table: str | None,
    used_ranges: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    category: str = category_module.DEFAULT_CATEGORY,
) -> list[Any]:
    api = client if client is not None else get_client()
    response = api.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=build_system_blocks(kb, category),
        tools=[SELECTION_TOOL],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(
                    transcription, max_candidates, prosody_table, used_ranges
                ),
            }
        ],
    )
    return _extract_candidates(response)


def select_clips(
    transcription: TranscriptionResult,
    kb: KnowledgeBase,
    client: Any | None = None,
    max_candidates: int = 8,
    snap: bool = True,
    silence_threshold: float = DEFAULT_SILENCE_GAP,
    model: str = MODEL_ID,
    max_tokens: int = 8000,
    prosody_table: str | None = None,
    enforce_duration_bounds: bool = False,
    used_ranges: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    category: str = category_module.DEFAULT_CATEGORY,
) -> list[ClipCandidate]:
    raw_candidates = _request_candidates(
        transcription,
        kb,
        client,
        max_candidates,
        model,
        max_tokens,
        prosody_table,
        used_ranges,
        category,
    )
    return validate_candidates(
        raw_candidates, transcription, snap, silence_threshold, enforce_duration_bounds
    )[:max_candidates]


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int], tolerance_words: int = 0) -> bool:
    """True se a sobreposicao entre os dois intervalos (em palavras) passa da tolerancia.
    Tolerancia 0 (default, todas as categorias exceto jogos) rejeita QUALQUER sobreposicao,
    igual ao comportamento original."""
    overlap_start = max(a[0], b[0])
    overlap_end = min(a[1], b[1])
    overlap_words = overlap_end - overlap_start + 1
    return overlap_words > tolerance_words


def filter_used_ranges(
    candidates: Sequence[ClipCandidate],
    used_ranges: Mapping[str, Sequence[tuple[int, int]]],
    overlap_tolerance_words: int = 0,
) -> list[ClipCandidate]:
    """Descarta candidato cujo intervalo de word_id sobrepoe um trecho ja usado NO MESMO
    formato alem da tolerancia - rede de seguranca contra o LLM ignorar a exclusao pedida
    no prompt. `overlap_tolerance_words` vem de `overlap_tolerance_words()`, categoria
    jogos permite um pedacinho de sobreposicao (ver instrucao de selecao)."""
    kept: list[ClipCandidate] = []
    for candidate in candidates:
        span = (candidate.start_word_id, candidate.end_word_id)
        if any(
            _ranges_overlap(span, used, overlap_tolerance_words)
            for used in used_ranges.get(candidate.format, ())
        ):
            continue
        kept.append(candidate)
    return kept


DEFAULT_MAX_SELECTION_ATTEMPTS = 4
DEFAULT_DRY_STREAK_LIMIT = 2


def select_clips_for_targets(
    transcription: TranscriptionResult,
    kb: KnowledgeBase,
    targets: Mapping[str, int],
    client: Any | None = None,
    used_ranges: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    snap: bool = True,
    silence_threshold: float = DEFAULT_SILENCE_GAP,
    model: str = MODEL_ID,
    max_tokens: int = 8000,
    prosody_table: str | None = None,
    enforce_duration_bounds: bool = True,
    max_attempts: int = DEFAULT_MAX_SELECTION_ATTEMPTS,
    dry_streak_limit: int = DEFAULT_DRY_STREAK_LIMIT,
    category: str = category_module.DEFAULT_CATEGORY,
) -> dict[str, list[ClipCandidate]]:
    """Chama a selecao repetidas vezes ate atingir `targets[formato]` candidatos NOVOS
    por formato (excluindo `used_ranges`, que sustenta "gerar mais" entre rodadas), ou
    desistir apos `max_attempts` tentativas ou `dry_streak_limit` rodadas seguidas sem
    NENHUM candidato novo valido - um video de 15min fisicamente nao cabe 5 clipes
    longos de 8-12min cada, entao a meta e "melhor esforco", nunca garantida.

    Devolve um dict `{formato: [candidatos novos]}` (so os NOVOS desta chamada, ja
    filtrados/validados/reparados - nao inclui os que geraram `used_ranges`)."""
    used = {clip_format: list(ranges) for clip_format, ranges in (used_ranges or {}).items()}
    collected: dict[str, list[ClipCandidate]] = {clip_format: [] for clip_format in targets}
    tolerance = overlap_tolerance_words(category)

    def still_needed() -> dict[str, int]:
        return {
            clip_format: target - len(collected[clip_format])
            for clip_format, target in targets.items()
            if len(collected[clip_format]) < target
        }

    dry_streak = 0
    attempt = 0
    remaining = still_needed()
    while remaining and attempt < max_attempts and dry_streak < dry_streak_limit:
        attempt += 1
        # Folga em cima do que falta: o LLM erra formato/duracao com frequencia, pedir
        # so o minimo faria a rodada terminar sistematicamente abaixo da meta.
        max_candidates = sum(remaining.values()) + len(remaining) + 2

        raw_candidates = _request_candidates(
            transcription,
            kb,
            client,
            max_candidates,
            model,
            max_tokens,
            prosody_table,
            used,
            category,
        )
        validated = validate_candidates(
            raw_candidates, transcription, snap, silence_threshold, enforce_duration_bounds
        )
        validated = filter_used_ranges(validated, used, tolerance)

        new_this_round = False
        for candidate in validated:
            if candidate.format not in targets:
                continue
            if len(collected[candidate.format]) >= targets[candidate.format]:
                continue
            collected[candidate.format].append(candidate)
            used.setdefault(candidate.format, []).append(
                (candidate.start_word_id, candidate.end_word_id)
            )
            new_this_round = True

        dry_streak = 0 if new_this_round else dry_streak + 1
        remaining = still_needed()

    return collected


def _extract_candidates(response: Any) -> list[Any]:
    for block in _attr(response, "content") or []:
        if _attr(block, "type") == "tool_use" and _attr(block, "name") == TOOL_NAME:
            payload = _attr(block, "input") or {}
            return list(payload.get("candidates", []))
    return []


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
