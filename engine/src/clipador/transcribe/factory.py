"""Escolha do transcriber por configuracao, com resolucao de device e fallback.

O DEFAULT DO PROJETO E O ELEVENLABS SCRIBE V2, por decisao medida em 2026-09-02 contra o
WhisperX local rodando no mesmo video. Ver
`.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md` para a comparacao completa.

Ordem de preferencia e por que:

1. `elevenlabs` (Scribe v2) - alinhamento por palavra proprio, nao derivado do Whisper;
   diarizacao inclusa; `no_verbatim` limpa gagueira, transforma numero por extenso em
   digito e converte a pontuacao ditada em voz alta ("Ponto:") no sinal de verdade.
   Na medicao ele acerta ~24 das 44 divergencias contra 1 do local, e evita dois casos de
   ALUCINACAO do local (texto inventado que passaria despercebido no clipe).
2. `assemblyai` - a outra opcao de nuvem, com alinhamento proprio. Preco parecido.
3. `whisperx` - melhor opcao LOCAL. Realinha o Whisper por CTC (wav2vec2), o que deixa o
   timestamp por palavra na casa de milissegundos em vez dos 200-300ms do Whisper puro.
   Use quando o audio nao pode sair da maquina, ou sem internet.
4. `faster-whisper` - ultimo recurso. Sem modelo de alinhamento: o timestamp por palavra
   volta a errar 200-300ms, o que aparece direto no karaoke da legenda.

Backend de nuvem SEM chave configurada e erro duro (`TranscriberConfigError`), nunca
queda silenciosa para o local: a diferenca entre os dois e de qualidade medida, e cair
sem avisar entregaria clipe pior sem ninguem perceber. Ja a queda de `whisperx` para
`faster-whisper` quando a lib nao esta instalada e aceitavel e sai com aviso no log, por
ser dependencia opcional e nao escolha editorial.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass

from clipador.transcribe.models import Transcriber
from clipador.transcribe.normalize import NormalizationRules
from clipador.transcribe.vocabulary import Vocabulary

logger = logging.getLogger(__name__)


class TranscriberConfigError(RuntimeError):
    """Configuracao de transcricao invalida: erro do usuario, com correcao conhecida."""


WHISPERX = "whisperx"
FASTER_WHISPER = "faster-whisper"
ASSEMBLYAI = "assemblyai"
ELEVENLABS = "elevenlabs"
BACKENDS = (WHISPERX, FASTER_WHISPER, ASSEMBLYAI, ELEVENLABS)

# Backends que rodam em nuvem: nao usam GPU local e mandam o audio pra fora.
CLOUD_BACKENDS = (ASSEMBLYAI, ELEVENLABS)

# ElevenLabs Scribe v2 e o default do projeto desde 2026-09-02, por decisao medida, nao
# por preferencia. Ver `.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md` para
# a comparacao completa contra o WhisperX local no video de teste. Resumo: das 44
# divergencias, o Scribe acerta ~24 e o local 1, e dois dos erros do local eram
# ALUCINACAO (texto inventado, gramaticalmente plausivel, que iria queimado no clipe).
# NAO troque este default de volta sem refazer a medicao.
DEFAULT_BACKEND = ELEVENLABS
# large-v3 e o maior modelo Whisper disponivel e a diferenca dele pro "medium" em PT-BR
# aparece justamente onde a legenda mais mostra: nome proprio, sigla e concordancia.
DEFAULT_MODEL_SIZE = "large-v3"


@dataclass(frozen=True)
class TranscriberSettings:
    backend: str = DEFAULT_BACKEND
    model_size: str = DEFAULT_MODEL_SIZE
    # "auto" resolve por presenca de CUDA; o WhisperX, diferente do faster-whisper, nao
    # entende "auto" e passa a string direto pro torch.
    device: str = "auto"
    compute_type: str = "auto"
    language: str | None = "pt"
    diarize: bool = False
    hf_token: str | None = None
    batch_size: int = 16
    assemblyai_api_key: str | None = None
    elevenlabs_api_key: str | None = None

    def __post_init__(self) -> None:
        if self.backend not in BACKENDS:
            raise ValueError(
                f"Backend de transcricao desconhecido: {self.backend!r}. Validos: {BACKENDS}"
            )


def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def resolve_compute_type(compute_type: str, device: str) -> str:
    """float16 so em GPU; em CPU o int8 e a unica combinacao que roda em tempo util."""
    if compute_type != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def _whisperx_available() -> bool:
    return importlib.util.find_spec("whisperx") is not None


# Variavel de ambiente que carrega a chave de cada backend de nuvem.
_API_KEY_ENV = {ELEVENLABS: "ELEVENLABS_API_KEY", ASSEMBLYAI: "ASSEMBLYAI_API_KEY"}


def resolve_api_key(backend: str, settings: TranscriberSettings) -> str | None:
    if backend == ELEVENLABS:
        return settings.elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY")
    if backend == ASSEMBLYAI:
        return settings.assemblyai_api_key or os.environ.get("ASSEMBLYAI_API_KEY")
    return None


def _require_api_key(backend: str, settings: TranscriberSettings) -> str:
    """Chave do backend de nuvem, ou erro que diz exatamente o que fazer.

    Falha ALTO em vez de cair no backend local: a diferenca entre nuvem e local aqui e de
    QUALIDADE de transcricao medida, nao de conveniencia (ver o comentario de
    DEFAULT_BACKEND). Um fallback silencioso entregaria clipe pior sem ninguem perceber,
    que e exatamente o modo de falha que este projeto evita.
    """
    api_key = resolve_api_key(backend, settings)
    if api_key:
        return api_key
    raise TranscriberConfigError(
        f"{_API_KEY_ENV[backend]} nao configurada, e {backend} e o backend de "
        "transcricao em uso. Coloque a chave no .env do engine, ou escolha um backend "
        "local explicitamente com `--transcriber whisperx` (qualidade menor, ver "
        ".docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md)."
    )


def build_transcriber(
    settings: TranscriberSettings = TranscriberSettings(),
    vocabulary: Vocabulary | None = None,
    normalization: NormalizationRules | None = NormalizationRules(),
) -> Transcriber:
    """Transcriber configurado, com device/compute_type ja resolvidos e logados."""
    vocabulary = vocabulary or Vocabulary()

    backend = settings.backend
    if backend == WHISPERX and not _whisperx_available():
        logger.warning(
            "whisperx nao esta instalado; caindo para faster-whisper. O timestamp por "
            "palavra fica ~200-300ms menos preciso, o que aparece no karaoke da legenda. "
            "Instale com `pip install -e .[video]` para recuperar o alinhamento CTC."
        )
        backend = FASTER_WHISPER

    # `model_size`/`device`/`compute_type` so existem para os backends LOCAIS. Loga-los
    # para um backend de nuvem imprimiria "elevenlabs large-v3 (cuda/float16)", que e
    # falso nos tres campos - e o log e o unico lugar onde se confere o que rodou de fato.
    if backend in CLOUD_BACKENDS:
        logger.info(
            "Transcriber: %s (nuvem), idioma=%s, diarizacao=%s, %d termo(s) de vocabulario",
            backend,
            settings.language,
            settings.diarize,
            len(vocabulary.terms),
        )
    else:
        # Resolver o device importa o torch; nao ha por que pagar isso em nuvem.
        device = resolve_device(settings.device)
        compute_type = resolve_compute_type(settings.compute_type, device)
        logger.info(
            "Transcriber: %s %s (%s/%s), idioma=%s, diarizacao=%s, %d termo(s) de vocabulario",
            backend,
            settings.model_size,
            device,
            compute_type,
            settings.language,
            settings.diarize,
            len(vocabulary.terms),
        )

    if backend == ELEVENLABS:
        from clipador.transcribe.elevenlabs_transcriber import ElevenLabsTranscriber

        return ElevenLabsTranscriber(
            api_key=_require_api_key(ELEVENLABS, settings),
            language_code=settings.language,
            diarize=settings.diarize,
            vocabulary=vocabulary,
            normalization=normalization,
        )

    if backend == ASSEMBLYAI:
        from clipador.transcribe.assemblyai_transcriber import AssemblyAITranscriber

        return AssemblyAITranscriber(
            api_key=_require_api_key(ASSEMBLYAI, settings),
            language_code=settings.language,
            diarize=settings.diarize,
            vocabulary=vocabulary,
            normalization=normalization,
        )

    if backend == WHISPERX:
        from clipador.transcribe.whisperx_transcriber import WhisperXTranscriber

        return WhisperXTranscriber(
            model_size=settings.model_size,
            device=device,
            compute_type=compute_type,
            language=settings.language,
            batch_size=settings.batch_size,
            diarize=settings.diarize,
            hf_token=settings.hf_token or os.environ.get("HUGGINGFACE_TOKEN"),
            vocabulary=vocabulary,
            normalization=normalization,
        )

    from clipador.transcribe.whisper import FasterWhisperTranscriber

    return FasterWhisperTranscriber(
        model_size=settings.model_size,
        device=device,
        compute_type=compute_type,
        language=settings.language,
        vocabulary=vocabulary,
        normalization=normalization,
    )
