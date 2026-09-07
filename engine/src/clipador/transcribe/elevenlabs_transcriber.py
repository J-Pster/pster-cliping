"""Transcricao via API da ElevenLabs (Scribe v2).

Escolhido como backend de nuvem preferido do projeto por tres motivos que valem
especificamente para legenda queimada, nao para transcricao em geral:

1. ALINHAMENTO PROPRIO. O Scribe nao e Whisper. As APIs que servem Whisper (Groq, OpenAI
   whisper-1) devolvem o timestamp por palavra nativo do decoder, com erro de 200-300ms,
   que e justamente o defeito que o `WhisperXTranscriber` local corrige com alinhamento
   CTC. Trocar por uma dessas seria economizar VRAM e perder a sincronia do karaoke.
2. TIMESTAMP POR CARACTERE, alem do por palavra (`timestamps_granularity="character"`).
   Nenhum concorrente da faixa oferece. Hoje o `Word` do projeto so guarda o intervalo da
   palavra inteira, entao o modo "word" e o default aqui; ver a nota em
   `TIMESTAMP_GRANULARITIES` sobre o que falta para aproveitar o nivel de caractere.
3. DIARIZACAO INCLUSA no preco, sem token do HuggingFace nem aceite de termos do pyannote.

O `speaker_id` alimenta apenas o cabecalho de cada segmento no prompt de selecao
(`select.selector.build_transcript_view`), nao decide corte nem export - por isso a
diarizacao ser de nuvem, e nao o pyannote local, tem consequencia baixa aqui.

Requer `ELEVENLABS_API_KEY` (ver `.env.example`) e o extra `cloud-transcribe`:
`pip install -e ".[cloud-transcribe]"`.
"""

from __future__ import annotations

import logging
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from clipador.transcribe.audio import extract_audio, needs_extraction, probe_duration_seconds
from clipador.transcribe.models import Segment, TranscriptionResult, Word, renumber_words
from clipador.transcribe.normalize import NormalizationRules, normalize_transcription
from clipador.transcribe.vocabulary import Vocabulary

logger = logging.getLogger(__name__)

MODEL_ID = "scribe_v2"

# "word" e o default: o schema de `Word` guarda um intervalo por palavra, e nada no
# pipeline consome caractere ainda. Passar para "character" so vale junto com uma versao
# de schema que carregue os caracteres ate o `subtitles.builder`, o que destravaria a
# varredura real dentro da palavra no modo `sweep` (hoje ela e interpolada linearmente).
TIMESTAMP_GRANULARITIES = ("word", "character")

# A resposta mistura tres tipos de token na mesma lista. Só `word` e fala; `spacing` sao
# os espacos entre palavras e `audio_event` sao marcacoes tipo "(risos)".
WORD_TOKEN_TYPE = "word"

# Limites do parametro `keyterms` da API. O vocabulario da KB (ver
# `clipador.transcribe.vocabulary`) e cortado para caber, em vez de deixar a API recusar
# a requisicao inteira por causa de um termo comprido.
MAX_KEYTERMS = 100
MAX_KEYTERM_CHARS = 50
MAX_KEYTERM_WORDS = 5

# O endpoint e SINCRONO: a conexao fica aberta durante todo o processamento. O default da
# SDK e 240s, e video longo estoura isso - um video de 81min falhou com `httpx.ReadTimeout`,
# e na rodada seguinte, ja com o teto corrigido, o mesmo audio levou 280s. Passou 40s do
# default, ou seja a margem era negativa.
#
# A razao tempo_api/duracao_audio NAO e constante, e por isso o teto e proporcional em vez
# de fixo. Medidas: 11min de audio -> 12s (razao 0.018); 81min -> 280s (razao 0.057). O
# arquivo maior e proporcionalmente mais lento, provavelmente upload mais fila.
#
# O timeout e REDE DE SEGURANCA, nao previsao: 0.5 da duracao deixa ~9x de folga sobre a
# pior razao medida, e ainda assim fecha a conexao em vez de pendurar o pipeline para
# sempre se a API travar.
TIMEOUT_DURATION_RATIO = 0.5
MIN_TIMEOUT_SECONDS = 600.0
# Sem duracao conhecida (ffprobe falhou), assume o pior caso plausivel em vez de arriscar
# um teto curto demais.
FALLBACK_TIMEOUT_SECONDS = 1800.0


class TranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SegmentRules:
    """Onde quebrar a lista plana de palavras em segmentos.

    A API devolve palavras, nao paragrafos. O prompt de selecao imprime um bloco por
    segmento com cabecalho de tempo e falante, entao um unico segmento de 40 minutos
    deixaria o LLM sem nenhuma estrutura para se orientar.
    """

    max_gap_seconds: float = 1.0
    max_seconds: float = 30.0


def _attr(source: Any, name: str, default: Any = None) -> Any:
    """A SDK devolve objetos; os testes injetam dicionarios. Ambos passam por aqui."""
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def valid_keyterms(vocabulary: Vocabulary) -> list[str]:
    """Vocabulario da KB no formato aceito pelo `keyterms`, validado na fronteira."""
    terms = [
        term
        for term in vocabulary.terms
        if len(term) <= MAX_KEYTERM_CHARS and len(term.split()) <= MAX_KEYTERM_WORDS
    ]
    return terms[:MAX_KEYTERMS]


def _spoken_words(raw_words: Sequence[Any]) -> list[Word]:
    words: list[Word] = []
    for raw in raw_words:
        if _attr(raw, "type", WORD_TOKEN_TYPE) != WORD_TOKEN_TYPE:
            continue
        text = str(_attr(raw, "text", "")).strip()
        start = _attr(raw, "start")
        end = _attr(raw, "end")
        if not text or start is None:
            continue
        start = float(start)
        words.append(
            Word(
                id=0,
                text=text,
                start=start,
                end=float(end) if end is not None else start,
                speaker=_attr(raw, "speaker_id"),
            )
        )
    return words


def split_into_segments(words: Sequence[Word], rules: SegmentRules) -> list[Segment]:
    """Quebra em troca de falante, silencio longo ou teto de duracao."""
    segments: list[Segment] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            segments.append(
                Segment(
                    id=0,
                    start=current[0].start,
                    end=current[-1].end,
                    text=" ".join(word.text for word in current),
                    words=list(current),
                    speaker=current[0].speaker,
                )
            )

    for word in words:
        if current and (
            word.speaker != current[0].speaker
            or word.start - current[-1].end > rules.max_gap_seconds
            or word.end - current[0].start > rules.max_seconds
        ):
            flush()
            current = []
        current.append(word)
    flush()
    return segments


def build_result_from_elevenlabs(
    response: Any,
    audio_path: str | Path | None = None,
    normalization: NormalizationRules | None = NormalizationRules(),
    segment_rules: SegmentRules = SegmentRules(),
    language: str | None = None,
) -> TranscriptionResult:
    """Converte a resposta do Scribe no schema estavel do projeto.

    `language` e o codigo que foi PEDIDO na requisicao e vence o que a resposta traz: o
    Scribe devolve ISO-639-3 ("por") e os backends locais gravam ISO-639-1 ("pt"), e o
    campo vai para o `transcription.json` em cache. Sem isso, o mesmo video teria idioma
    diferente no arquivo dependendo de qual backend rodou.
    """
    words = _spoken_words(_attr(response, "words") or [])
    segments = split_into_segments(words, segment_rules)
    renumber_words(segments)

    result = TranscriptionResult(
        segments=segments,
        language=language or _attr(response, "language_code"),
        duration=_attr(response, "audio_duration_secs")
        or max((segment.end for segment in segments), default=None),
        audio_path=None if audio_path is None else str(audio_path),
    )
    return result if normalization is None else normalize_transcription(result, normalization)


class ElevenLabsTranscriber:
    """Transcriber via Scribe v2. Mesmo contrato: `transcribe(audio_path) -> TranscriptionResult`.

    Args:
        api_key: chave da ElevenLabs. Obrigatoria a menos que `client_factory` seja
            passado (uso em teste).
        language_code: ISO-639-1 do audio, default "pt".
        diarize: liga a diarizacao (inclusa no preco, ate 32 falantes).
        no_verbatim: limpa a transcricao em vez de reproduzir o audio literalmente.
            LIGADO por padrao, com base em medicao no video de teste (11 min, PT-BR):
            - "Ponto:" ditado pelo narrador ao ler uma lista vira o sinal `.` de verdade,
              em vez de virar a palavra "Ponto" queimada na legenda (8 ocorrencias);
            - numero por extenso vira digito ("vinte por cento" -> "20%"), que le melhor
              e ocupa menos largura na cue;
            - gagueira e falso comeco somem ("preventida-prevent-preventivas" ->
              "preventivas", "No-- na" -> "Na"): 5 tokens de lixo -> 0.
            Custo: a caixa de nome proprio composto se perde ("Direito Penal" vira
            "direito penal"), o que e invisivel nos presets em caixa alta e uma perda
            pequena no preset `classico`.
        timestamps_granularity: "word" (default) ou "character". Ver TIMESTAMP_GRANULARITIES.
        vocabulary: termos de dominio da KB, enviados como `keyterms`.
        extract_audio_first: extrai a trilha de audio antes de subir. Ligado por padrao -
            o pipeline entrega o caminho do VIDEO, e subir 2GB em vez de 14MB domina o
            tempo total da etapa. Ver `clipador.transcribe.audio`.
        client_factory: injecao do client para teste. Sem ele, a SDK oficial
            (`elevenlabs`) so e importada na primeira transcricao.
    """

    def __init__(
        self,
        api_key: str | None = None,
        language_code: str | None = "pt",
        diarize: bool = True,
        no_verbatim: bool = True,
        timestamps_granularity: str = "word",
        vocabulary: Vocabulary | None = None,
        normalization: NormalizationRules | None = NormalizationRules(),
        segment_rules: SegmentRules = SegmentRules(),
        extract_audio_first: bool = True,
        timeout_seconds: float | None = None,
        client_factory: Callable[[], Any] | None = None,
        audio_extractor: Callable[..., Path] = extract_audio,
    ) -> None:
        if timestamps_granularity not in TIMESTAMP_GRANULARITIES:
            raise ValueError(
                f"timestamps_granularity invalido: {timestamps_granularity!r}. "
                f"Validos: {TIMESTAMP_GRANULARITIES}"
            )
        self.api_key = api_key
        self.language_code = language_code
        self.diarize = diarize
        self.no_verbatim = no_verbatim
        self.timestamps_granularity = timestamps_granularity
        self.vocabulary = vocabulary or Vocabulary()
        self.normalization = normalization
        self.segment_rules = segment_rules
        self.extract_audio_first = extract_audio_first
        self.timeout_seconds = timeout_seconds
        self._client_factory = client_factory
        self._audio_extractor = audio_extractor
        self._client: Any | None = None

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client

        # A checagem da chave vem ANTES do import: sao duas falhas de configuracao
        # diferentes (chave ausente x extra nao instalado) e cada uma tem a sua correcao.
        # Importando primeiro, quem so esqueceu a chave recebia um ModuleNotFoundError
        # que nao diz nada sobre o problema real.
        if not self.api_key:
            raise TranscriptionError(
                "ELEVENLABS_API_KEY nao configurada. Gere a chave em elevenlabs.io "
                "(menu do perfil > API Keys) e coloque no .env do engine."
            )
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError as exc:
            raise TranscriptionError(
                'SDK da ElevenLabs nao instalada. Rode `pip install -e ".[cloud-transcribe]"` '
                "a partir de engine/."
            ) from exc

        self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def _request_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "model_id": MODEL_ID,
            "diarize": self.diarize,
            "no_verbatim": self.no_verbatim,
            "timestamps_granularity": self.timestamps_granularity,
            # Desligado: com o default (ligado) a resposta inclui tokens do tipo
            # `audio_event` ("(risos)") que nao sao fala e nao devem virar legenda.
            "tag_audio_events": False,
        }
        if self.language_code:
            options["language_code"] = self.language_code
        keyterms = valid_keyterms(self.vocabulary)
        if keyterms:
            options["keyterms"] = keyterms
        return options

    def _timeout_for(self, upload_path: Path) -> float:
        """Teto de espera da chamada, proporcional a duracao do audio.

        Ver TIMEOUT_DURATION_RATIO: o endpoint e sincrono e o default de 240s da SDK
        estoura em video longo.
        """
        if self.timeout_seconds is not None:
            return self.timeout_seconds
        try:
            duration = probe_duration_seconds(upload_path)
        except Exception as exc:  # ffprobe ausente ou arquivo ilegivel
            logger.warning("Nao foi possivel medir a duracao de %s: %s", upload_path, exc)
            duration = None
        if duration is None:
            return FALLBACK_TIMEOUT_SECONDS
        return max(MIN_TIMEOUT_SECONDS, duration * TIMEOUT_DURATION_RATIO)

    def _upload_source(self, audio_path: Path, temp_dir: str) -> Path:
        if not self.extract_audio_first or not needs_extraction(audio_path):
            return audio_path
        return self._audio_extractor(audio_path, Path(temp_dir) / "audio.ogg")

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        client = self._load_client()
        audio_path = Path(audio_path)
        options = self._request_options()

        with tempfile.TemporaryDirectory(prefix="clipador-scribe-") as temp_dir:
            upload_path = self._upload_source(audio_path, temp_dir)
            size_mb = upload_path.stat().st_size / 1_048_576 if upload_path.is_file() else 0.0
            logger.info(
                "ElevenLabs Scribe: enviando %s (%.1f MB, diarizacao=%s, %d keyterm(s))",
                upload_path.name,
                size_mb,
                self.diarize,
                len(options.get("keyterms", [])),
            )
            timeout = self._timeout_for(upload_path)
            logger.info("ElevenLabs Scribe: teto de espera desta chamada %.0fs", timeout)
            stage_start = time.monotonic()
            with upload_path.open("rb") as stream:
                response = client.speech_to_text.convert(
                    file=stream,
                    request_options={"timeout_in_seconds": int(timeout)},
                    **options,
                )
            elapsed = time.monotonic() - stage_start

        # Nao ha checagem de campo de erro na resposta: a SDK levanta `ApiError` com
        # status e corpo quando a API recusa, e a resposta de sucesso nao tem campo de
        # erro nenhum. `TranscriptionError` aqui e so pra erro de CONFIGURACAO (chave
        # ausente, extra nao instalado), que e o que o usuario consegue corrigir.
        logger.info("ElevenLabs Scribe: transcricao concluida em %.1fs", elapsed)
        return build_result_from_elevenlabs(
            response,
            audio_path=audio_path,
            normalization=self.normalization,
            segment_rules=self.segment_rules,
            language=self.language_code,
        )
