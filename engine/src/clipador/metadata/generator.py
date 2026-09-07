"""Geracao de titulo/descricao/hashtags via LLM, reaproveitando o dossie da KB como prefixo estavel."""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from clipador import category as category_module
from clipador.kb.knowledge import KnowledgeBase, TopicMatch, search_topics
from clipador.llm.provider import MODEL_ID, get_client
from clipador.metadata.censor import censor_text
from clipador.metadata.models import ClipMetadata
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT, ClipCandidate

logger = logging.getLogger(__name__)

TOOL_NAME = "propose_metadata"
MAX_HEADLINE_WORDS = 4
# Fracao minima do texto da headline que pode coincidir com um trecho continuo da
# transcricao antes de considerarmos "e so uma citacao com outras palavras em volta" e
# descartarmos a headline (o composer trata "" como sem texto).
HEADLINE_TRANSCRIPT_OVERLAP_RATIO = 0.6
# Quantas vezes pede pro LLM refletir e propor OUTRA headline depois que a anterior foi
# rejeitada (comprida demais ou citacao literal), antes de desistir e deixar o clipe sem
# headline. Bounded de proposito: e um reparo, nao um loop ate acertar.
MAX_HEADLINE_REPAIR_ATTEMPTS = 2

MIN_KEYWORD_LENGTH = 5
MAX_TOPIC_MATCHES = 3

# Teto de hashtags. Acima disso a lista vira ruido: o algoritmo das plataformas usa a
# hashtag como sinal de TEMA, e uma lista longa dilui esse sinal em vez de reforca-lo.
MAX_HASHTAGS = 5
# Tudo que nao seja letra, digito ou underscore sai da hashtag. O caso que motivou isto foi
# o LLM devolver "seguranca publica" e "crime organizado" como UMA hashtag cada: publicado,
# `#seguranca publica` vira a tag `#seguranca` mais a palavra solta "publica", e o termo que
# importava (a expressao inteira) se perde. Acento fica, e valido em hashtag nas plataformas.
_HASHTAG_INVALID_CHARS = re.compile(r"[^\w]", re.UNICODE)

# Hashtags de alcance generico, que nao dizem nada sobre o conteudo. A plataforma ja sabe
# o formato pelo proprio upload (vertical curto e Short/Reel sem precisar de #shorts), e
# marcar isso no texto so gasta uma das 5 vagas de tema.
BANNED_HASHTAGS = frozenset(
    {
        "shorts", "short", "reels", "reel", "tiktok", "fyp", "fy", "foryou",
        "foryoupage", "viral", "viralvideo", "trending", "explore", "explorepage",
    }
)

_KEYWORD_STRIP_CHARS = ".,!?;:\"'()[]{}"


def _extract_keywords(text: str) -> list[str]:
    """Palavras de conteudo (>=5 letras) do trecho, sem duplicata - proxy barato de
    'termos que provavelmente aparecem tambem nos arquivos de topico', sem precisar de
    NLP nem de mais uma chamada de LLM so pra extrair palavra-chave."""
    words = {w.strip(_KEYWORD_STRIP_CHARS).lower() for w in text.split()}
    return sorted(w for w in words if len(w) >= MIN_KEYWORD_LENGTH)


def _relevant_topic_matches(kb: KnowledgeBase, transcription_excerpt: str) -> list[TopicMatch]:
    """Roda search_topics uma vez por palavra-chave do trecho (comportamento OR entre
    palavras, ja que search_topics faz AND entre os termos de uma unica chamada - uma
    chamada por palavra e o jeito mais simples de aproximar OR sem mexer em knowledge.py),
    agrega por (documento, heading) mantendo o maior score, ordena decrescente."""
    best: dict[tuple[str, str], TopicMatch] = {}
    for keyword in _extract_keywords(transcription_excerpt):
        for match in search_topics(kb, keyword, max_results=MAX_TOPIC_MATCHES):
            key = (match.document, match.heading)
            if key not in best or match.score > best[key].score:
                best[key] = match
    return sorted(best.values(), key=lambda m: -m.score)[:MAX_TOPIC_MATCHES]

_HEADLINE_EXAMPLES_BY_CATEGORY: dict[str, str] = {
    category_module.POLITICS_PERSON: (
        "Exemplos BONS (tema especifico, gancho, nao e citacao literal): trecho "
        "sobre prisao preventiva por posse de fuzil -> 'FUZIL PRENDE OU NAO?'; "
        "trecho sobre indicadores de gestao municipal -> '10 METAS PRA PREFEITOS'. "
        "Exemplos RUINS (proibidos): genericos sem tema, serviriam pra qualquer "
        "video -> 'ISSO MUDOU TUDO', 'A VERDADE INCOMODA', 'ELE PERDEU A CALMA'; "
        "OU citam a fala literal -> 'a tutela precisa ser antecipada'."
    ),
    category_module.GAMING: (
        "Exemplos BONS (highlight especifico, gancho, nao e citacao literal): trecho "
        "de uma eliminacao contra o time inteiro -> 'ELIMINEI O TIME TODO'; trecho de "
        "uma jogada de virada nos ultimos segundos -> 'CLUTCH IMPOSSIVEL'. "
        "Exemplos RUINS (proibidos): genericos sem highlight, serviriam pra qualquer "
        "video -> 'VOCE NAO VAI ACREDITAR', 'ISSO FOI INSANO'; OU citam a fala literal "
        "do jogador -> 'caraca eu consegui'."
    ),
    category_module.BOOK_AUDIOBOOK: (
        "O livro normalmente e de nao-ficcao (politica, estrategia, negocios, tecnico, "
        "ensaio), entao a headline nomeia um ARGUMENTO ou INSIGHT especifico, nunca uma "
        "virada de enredo/personagem. Exemplos BONS (argumento especifico, gancho, nao e "
        "citacao literal): trecho sobre como incentivos mal desenhados destroem uma "
        "politica publica -> 'O INCENTIVO ERRADO MATA'; trecho sobre uma regra de "
        "negociacao contraintuitiva -> 'NUNCA ACEITE A 1a OFERTA'. "
        "Exemplos RUINS (proibidos): genericos sem argumento, serviriam pra qualquer "
        "livro -> 'VOCE PRECISA OUVIR ISSO', 'O CAPITULO MAIS FORTE'; OU citam a fala "
        "literal do autor/narrador -> 'entao o que eu quero dizer e o seguinte'."
    ),
}


def _thumbnail_headline_property(category: str) -> dict[str, Any]:
    """Schema do campo `thumbnail_headline`, compartilhado entre a tool principal
    (`build_metadata_tool`) e a tool de reparo (`build_headline_repair_tool`) - a regra
    e uma so, nunca duas copias que podem divergir."""
    examples = _HEADLINE_EXAMPLES_BY_CATEGORY[category_module.validate_category(category)]
    return {
        "type": "string",
        "maxLength": 28,
        "description": (
            "Manchete de NO MAXIMO 4 palavras (28 caracteres) para ser escrita por "
            "cima da thumbnail, curta o bastante pra ler em 1 segundo numa tela de "
            "celular. Regra tripla, as tres ao mesmo tempo: "
            "(1) tem que citar o ASSUNTO REAL e ESPECIFICO deste trecho (um termo/tema "
            "concreto do que esta sendo mostrado aqui, nao de outro trecho do video) - "
            "PROIBIDO uma frase generica de clickbait que serviria pra qualquer video "
            "qualquer, sem ligacao clara com o conteudo especifico deste clipe; "
            "(2) PROIBIDO citar ou parafrasear a fala literal da transcricao: a legenda "
            "queimada ja mostra a fala, repeti-la na imagem e exatamente o que se quer "
            "evitar; (3) tem que ser uma frase COMPLETA que faz sentido sozinha dentro do "
            "limite de 4 palavras - NUNCA escreva uma frase mais longa esperando que ela "
            "seja cortada depois: se nao cabe inteira e com sentido em 4 palavras, "
            "reescreva a ideia numa frase mais curta, nao mande o comeco de uma frase "
            "maior. O equilibrio certo: nomeie o TEMA especifico como gancho (pergunta, "
            "contradicao ou afirmacao de impacto SOBRE ESSE TEMA), nunca as palavras "
            f"exatas da fala nem uma frase vaga sem tema nenhum. {examples}"
        ),
    }


def build_metadata_tool(category: str = category_module.DEFAULT_CATEGORY) -> dict[str, Any]:
    """Schema da tool `propose_metadata`, com exemplos de headline especificos da categoria
    embutidos na description (o modelo segue exemplo em contexto melhor que regra abstrata)."""
    return {
        "name": TOOL_NAME,
        "description": (
            "Registra titulo, descricao, hashtags e a headline da thumbnail do clipe, citando "
            "os elementos do dossie que foram efetivamente usados."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo do clipe."},
                "description": {"type": "string", "description": "Descricao do clipe."},
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    # NAO adicionar `maxItems` aqui: a API da Anthropic recusa a requisicao
                    # inteira com "For 'array' type, property 'maxItems' is not supported".
                    # O teto vive na descricao (pedido ao modelo) e em `sanitize_hashtags`
                    # (garantia deterministica na volta), que e onde ele tem que estar.
                    "description": (
                        f"No maximo {MAX_HASHTAGS} hashtags, sem o caractere '#' e SEM ESPACO "
                        "(cada hashtag e uma palavra so; para expressao composta, junte as "
                        "palavras, ex.: 'crimeorganizado'). Devem sair do "
                        "ASSUNTO REAL deste trecho: o tema tratado, a pessoa ou instituicao "
                        "citada, o termo tecnico central, a obra. Nada de marcador generico de "
                        "alcance (shorts, reels, tiktok, fyp, viral, trending) - a plataforma "
                        "ja sabe o formato pelo upload e essas tags gastam vaga sem dizer nada "
                        "sobre o conteudo. Prefira poucas e especificas a muitas e vagas."
                    ),
                },
                "kb_references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Elementos verificaveis do dossie citados/usados (pauta, termo do "
                        "glossario, fato biografico). Pode ficar vazio se nada do dossie se aplicar."
                    ),
                },
                "thumbnail_headline": _thumbnail_headline_property(category),
            },
            "required": [
                "title",
                "description",
                "hashtags",
                "kb_references",
                "thumbnail_headline",
            ],
            "additionalProperties": False,
        },
    }


HEADLINE_REPAIR_TOOL_NAME = "propose_thumbnail_headline"


def build_headline_repair_tool(category: str = category_module.DEFAULT_CATEGORY) -> dict[str, Any]:
    """Tool minima pra pedir uma SEGUNDA tentativa de `thumbnail_headline`, depois que a
    primeira foi rejeitada (passou das 4 palavras ou citou a fala quase literalmente).
    Reaproveita a mesma definicao de campo da tool principal, ver `_thumbnail_headline_property`."""
    return {
        "name": HEADLINE_REPAIR_TOOL_NAME,
        "description": (
            "Propoe uma NOVA manchete de thumbnail, depois que a anterior foi rejeitada "
            "por passar do limite de palavras ou por citar a fala literal."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"thumbnail_headline": _thumbnail_headline_property(category)},
            "required": ["thumbnail_headline"],
            "additionalProperties": False,
        },
    }


# Mantido para quem ainda importa o nome antigo diretamente: sempre a variante politico/pessoa.
METADATA_TOOL: dict[str, Any] = build_metadata_tool(category_module.POLITICS_PERSON)

_POLITICS_PERSON_BASE_INSTRUCTIONS = """Voce escreve titulo, descricao e hashtags para um clipe de video de um movimento politico.

Regras inegociaveis:
- O texto deve refletir vocabulario, pautas e tom de voz reais do dossie abaixo, nunca um texto generico de "video politico qualquer".
- Sempre que possivel, cite pelo menos um elemento verificavel do dossie (pauta, termo do glossario, ou fato biografico) e registre-o em kb_references.
- Nao invente fatos que nao estejam no dossie nem na transcricao do trecho.
- Se nada do dossie realmente se aplicar ao trecho, deixe kb_references vazio em vez de forcar uma citacao artificial.
- thumbnail_headline e um gancho de 1 a 4 palavras para a imagem da thumbnail sobre o TEMA ESPECIFICO deste trecho (nao um clickbait generico que serviria pra qualquer video), e ao mesmo tempo nunca a fala literal do trecho: o video ja mostra a fala em legenda queimada, entao citar ou parafrasear a transcricao ali e erro. Nomeie o assunto especifico como gancho (pergunta, contradicao ou afirmacao de impacto sobre esse assunto).

Responda exclusivamente chamando a ferramenta propose_metadata."""

_GAMING_BASE_INSTRUCTIONS = """Voce escreve titulo, descricao e hashtags para um clipe de gameplay (video de um jogo).

Regras inegociaveis:
- O texto deve refletir o vocabulario real do jogo/genero e o tom de voz do dossie abaixo (quando houver), nunca um texto generico de "video de jogo qualquer".
- Sempre que possivel, cite pelo menos um elemento verificavel do dossie (nome do jogo, modo, personagem, apelido do canal) e registre-o em kb_references.
- Nao invente fatos que nao estejam no dossie nem na transcricao do trecho (ex.: nao invente nome de jogo ou personagem que nao apareceu).
- Se nada do dossie realmente se aplicar ao trecho, deixe kb_references vazio em vez de forcar uma citacao artificial.
- thumbnail_headline e um gancho de 1 a 4 palavras sobre o HIGHLIGHT ESPECIFICO deste trecho (eliminacao, clutch, virada, momento comico - nao um clickbait generico que serviria pra qualquer clipe de jogo), e ao mesmo tempo nunca a fala literal do jogador: o video ja mostra a fala em legenda queimada, entao citar ou parafrasear a transcricao ali e erro. Nomeie o highlight especifico como gancho.

Responda exclusivamente chamando a ferramenta propose_metadata."""

_BOOK_AUDIOBOOK_BASE_INSTRUCTIONS = """Voce escreve titulo, descricao e hashtags para um clipe de audiobook (narracao/leitura de livro), normalmente de nao-ficcao (politica, estrategia, negocios, tecnico, ensaio) - nao trate o livro como romance.

Regras inegociaveis:
- O texto deve refletir o tom, o assunto e o vocabulario reais do livro/dossie abaixo, nunca um texto generico de "trecho de livro qualquer".
- Sempre que possivel, cite pelo menos um elemento verificavel do dossie (titulo do livro, autor, conceito-chave, capitulo) e registre-o em kb_references.
- Nao invente fatos que nao estejam no dossie nem na transcricao do trecho (ex.: nao invente dado, estatistica ou conceito que nao apareceu no trecho).
- Se nada do dossie realmente se aplicar ao trecho, deixe kb_references vazio em vez de forcar uma citacao artificial.
- thumbnail_headline e um gancho de 1 a 4 palavras sobre o ARGUMENTO/INSIGHT ESPECIFICO deste trecho (nao um clickbait generico que serviria pra qualquer livro), e ao mesmo tempo nunca a fala literal do autor/narrador: o video ja mostra a fala em legenda queimada, entao citar ou parafrasear a transcricao ali e erro. Nomeie o argumento/insight especifico como gancho.

Responda exclusivamente chamando a ferramenta propose_metadata."""

BASE_INSTRUCTIONS_BY_CATEGORY: dict[str, str] = {
    category_module.POLITICS_PERSON: _POLITICS_PERSON_BASE_INSTRUCTIONS,
    category_module.GAMING: _GAMING_BASE_INSTRUCTIONS,
    category_module.BOOK_AUDIOBOOK: _BOOK_AUDIOBOOK_BASE_INSTRUCTIONS,
}

# Mantido para quem ainda importa o nome antigo diretamente: sempre a variante politico/pessoa.
BASE_INSTRUCTIONS = _POLITICS_PERSON_BASE_INSTRUCTIONS

FORMAT_INSTRUCTIONS: dict[str, str] = {
    SHORT_FORMAT: (
        "Formato deste clipe: vertical curto (short/reels/TikTok). Copy direta, gancho forte "
        "nos primeiros segundos do titulo e da descricao, frases curtas."
    ),
    LONG_FORMAT: (
        "Formato deste clipe: horizontal longo (YouTube). Descricao mais completa, "
        "contextualizando o trecho sem depender de um gancho de 3 segundos."
    ),
}


def build_system_blocks(
    kb: KnowledgeBase, clip_format: str, category: str = category_module.DEFAULT_CATEGORY
) -> list[dict[str, Any]]:
    """Prefixo estavel (instrucoes da categoria + dossie, cache marcado) seguido da
    instrucao especifica do formato."""
    instructions = BASE_INSTRUCTIONS_BY_CATEGORY[category_module.validate_category(category)]
    blocks: list[dict[str, Any]] = [{"type": "text", "text": instructions}]
    dossier = kb.dossier()
    if dossier:
        blocks.append({"type": "text", "text": dossier})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}

    format_instruction = FORMAT_INSTRUCTIONS.get(clip_format, "")
    if format_instruction:
        blocks.append({"type": "text", "text": format_instruction})
    return blocks


def sanitize_hashtags(raw: Sequence[Any]) -> list[str]:
    """Rede de seguranca determinista para a lista de hashtags do LLM.

    O `maxItems` do schema e a instrucao no prompt sao PEDIDO; isto aqui e a garantia. O
    modelo continua devolvendo marcador generico de vez em quando (o corpus de treino esta
    cheio de "#shorts #viral"), e o arquivo `ready-to-post.txt` vai direto pro copiar e
    colar, sem ninguem revisar tag por tag.

    Normaliza tirando o '#', descarta banida e duplicata (sem diferenciar caixa) e corta
    em MAX_HASHTAGS preservando a ordem, que e a de relevancia dada pelo modelo.
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        tag = _HASHTAG_INVALID_CHARS.sub("", str(item).lstrip("#"))
        if not tag:
            continue
        key = tag.casefold()
        if key in BANNED_HASHTAGS:
            logger.info("Hashtag generica descartada: #%s", tag)
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)
    if len(result) > MAX_HASHTAGS:
        logger.info(
            "Hashtags cortadas de %d para %d (as %d menos relevantes foram descartadas).",
            len(result),
            MAX_HASHTAGS,
            len(result) - MAX_HASHTAGS,
        )
    return result[:MAX_HASHTAGS]


def _headline_rejection_reason(headline: str, transcription_excerpt: str) -> str | None:
    """Motivo pra rejeitar a headline (texto pronto pra virar o prompt de reparo), ou
    None quando ela e valida. Fonte unica de verdade pras duas checagens - `sanitize_headline`
    usa isto pra decidir aceitar/descartar, `generate_metadata` usa pra explicar o motivo
    ao LLM na segunda tentativa."""
    text = headline.strip()
    if not text:
        return None

    words = text.split()
    if len(words) > MAX_HEADLINE_WORDS:
        return (
            f"tem {len(words)} palavras, o maximo e {MAX_HEADLINE_WORDS} - nao mande so "
            "as primeiras palavras de uma frase maior, reescreva a ideia como uma frase "
            "CURTA e COMPLETA que cabe inteira no limite"
        )

    matcher = difflib.SequenceMatcher(None, text.lower(), transcription_excerpt.lower())
    overlap = matcher.find_longest_match(0, len(text), 0, len(transcription_excerpt)).size
    if overlap > len(text) * HEADLINE_TRANSCRIPT_OVERLAP_RATIO:
        return (
            "e quase identica a uma citacao literal da transcricao - proponha um gancho "
            "original sobre o TEMA do trecho, nao as palavras exatas da fala"
        )

    return None


def sanitize_headline(headline: str, transcription_excerpt: str) -> str:
    """Portao deterministico final: aceita a headline como veio quando ela cabe em
    `MAX_HEADLINE_WORDS` e nao e so uma citacao literal da fala, ou descarta (devolve "")
    quando nao cabe - o composer ja trata headline vazia como "sem texto", nunca quebra.

    NUNCA trunca mecanicamente pra `MAX_HEADLINE_WORDS` palavras: cortar uma frase maior
    nas primeiras N palavras produz fragmento sem sentido (ex.: "MULTA QUE ACABA COM"
    cortado de "MULTA QUE ACABA COM O TRAFICANTE"), que e pior que nao ter headline
    nenhuma. Quem tenta CONSERTAR uma headline rejeitada pedindo outra ao LLM e
    `generate_metadata` (ver `_headline_rejection_reason` e `build_headline_repair_tool`),
    isto aqui so decide aceitar ou descartar o que chegou.
    """
    text = headline.strip()
    if not text:
        return ""

    reason = _headline_rejection_reason(text, transcription_excerpt)
    if reason is not None:
        logger.warning("thumbnail_headline %r descartada: %s.", text, reason)
        return ""
    return text


def build_user_prompt(
    candidate: ClipCandidate,
    transcription_excerpt: str,
    topic_matches: Sequence[TopicMatch] = (),
) -> str:
    prompt = (
        f"Trecho selecionado (formato {candidate.format}, {candidate.duration:.1f}s, "
        f"score {candidate.score}).\n"
        f"Justificativa da selecao original: {candidate.justificativa}\n\n"
        f"Transcricao do trecho:\n{transcription_excerpt}"
    )
    if topic_matches:
        excerpts = "\n\n".join(
            f"[{m.document} - {m.heading}]\n{m.excerpt}" for m in topic_matches
        )
        prompt += f"\n\nTrechos relevantes da base de topicos (kb/topics/):\n{excerpts}"
    return prompt


def _repair_headline(
    api: Any,
    model: str,
    max_tokens: int,
    candidate: ClipCandidate,
    transcription_excerpt: str,
    kb: KnowledgeBase,
    category: str,
    topic_matches: Sequence[TopicMatch],
    rejected_headline: str,
    reason: str,
) -> str:
    """Segunda chamada, focada so na headline: quando a primeira nao serve, pede pro LLM
    REFLETIR sobre o motivo da rejeicao e propor outra - em vez de cortar mecanicamente as
    primeiras palavras da rejeitada (o que produz fragmento sem sentido), quem decide a
    frase substituta continua sendo o modelo, agora com o proprio erro como contexto."""
    prompt = (
        f"{build_user_prompt(candidate, transcription_excerpt, topic_matches)}\n\n"
        f"Sua manchete anterior ('{rejected_headline}') foi rejeitada: {reason}. Proponha "
        "OUTRA manchete pra esta thumbnail, sem repetir o mesmo erro."
    )
    response = api.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=build_system_blocks(kb, candidate.format, category),
        tools=[build_headline_repair_tool(category)],
        tool_choice={"type": "tool", "name": HEADLINE_REPAIR_TOOL_NAME},
        messages=[{"role": "user", "content": prompt}],
    )
    payload = _extract_payload(response, HEADLINE_REPAIR_TOOL_NAME)
    return str(payload.get("thumbnail_headline", ""))


def generate_metadata(
    candidate: ClipCandidate,
    transcription_excerpt: str,
    kb: KnowledgeBase,
    client: Any | None = None,
    model: str = MODEL_ID,
    max_tokens: int = 2000,
    category: str = category_module.DEFAULT_CATEGORY,
) -> ClipMetadata:
    api = client if client is not None else get_client()
    topic_matches = _relevant_topic_matches(kb, transcription_excerpt)
    response = api.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=build_system_blocks(kb, candidate.format, category),
        tools=[build_metadata_tool(category)],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(candidate, transcription_excerpt, topic_matches),
            }
        ],
    )

    payload = _extract_payload(response)
    kb_references = [str(ref) for ref in payload.get("kb_references", [])]
    if not kb_references:
        logger.warning(
            "Metadados gerados sem kb_references (titulo=%r); nenhum elemento verificavel "
            "da base de conhecimento foi citado.",
            payload.get("title", ""),
        )

    raw_headline = str(payload.get("thumbnail_headline", ""))
    headline = sanitize_headline(raw_headline, transcription_excerpt)
    attempted = raw_headline
    for _ in range(MAX_HEADLINE_REPAIR_ATTEMPTS):
        if headline or not attempted.strip():
            break
        # A headline existia mas foi rejeitada (comprida demais ou citacao literal) - em
        # vez de aceitar um fragmento cortado sem sentido, ou desistir na primeira, da mais
        # uma chance pro LLM com o motivo da rejeicao em maos, ate o teto de tentativas.
        reason = _headline_rejection_reason(attempted, transcription_excerpt) or ""
        attempted = _repair_headline(
            api,
            model,
            max_tokens,
            candidate,
            transcription_excerpt,
            kb,
            category,
            topic_matches,
            attempted,
            reason,
        )
        headline = sanitize_headline(attempted, transcription_excerpt)
    if not headline and raw_headline.strip():
        logger.warning(
            "thumbnail_headline sem versao valida apos reparo (ultima tentativa: %r); "
            "clipe sai sem headline.",
            attempted,
        )

    return ClipMetadata(
        title=censor_text(str(payload.get("title", ""))),
        description=censor_text(str(payload.get("description", ""))),
        hashtags=sanitize_hashtags(payload.get("hashtags", [])),
        format=candidate.format,
        kb_references=kb_references,
        thumbnail_headline=censor_text(headline),
    )


def _extract_payload(response: Any, tool_name: str = TOOL_NAME) -> Mapping[str, Any]:
    for block in _attr(response, "content") or []:
        if _attr(block, "type") == "tool_use" and _attr(block, "name") == tool_name:
            return _attr(block, "input") or {}
    return {}


def _attr(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)
