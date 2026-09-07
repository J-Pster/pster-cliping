"""Testes do ElevenLabsTranscriber (Scribe v2) - 100% offline, client sempre injetado."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clipador.transcribe import elevenlabs_transcriber
from clipador.transcribe.audio import extract_audio, needs_extraction
from clipador.transcribe.elevenlabs_transcriber import (
    FALLBACK_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    MODEL_ID,
    ElevenLabsTranscriber,
    SegmentRules,
    TranscriptionError,
    build_result_from_elevenlabs,
    split_into_segments,
    valid_keyterms,
)
from clipador.transcribe.factory import TranscriberSettings, build_transcriber
from clipador.transcribe.models import Word
from clipador.transcribe.vocabulary import Vocabulary


def _token(text, start, end, type_="word", speaker_id=None):
    return SimpleNamespace(text=text, start=start, end=end, type=type_, speaker_id=speaker_id)


def _response(words, language_code="pt", audio_duration_secs=None):
    return SimpleNamespace(
        words=words, language_code=language_code, audio_duration_secs=audio_duration_secs
    )


class FakeClient:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

        outer = self

        class _SpeechToText:
            def convert(self, **kwargs):
                outer.calls.append(kwargs)
                return outer.response

        self.speech_to_text = _SpeechToText()


def _fake_media(tmp_path: Path, name: str = "video.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"conteudo de midia falso")
    return path


def _transcriber(response, **overrides) -> ElevenLabsTranscriber:
    base = {
        "client_factory": lambda: FakeClient(response),
        "extract_audio_first": False,
    }
    return ElevenLabsTranscriber(**{**base, **overrides})


# --------------------------------------------------------------- parse da resposta


def test_descarta_tokens_de_espacamento():
    """A resposta mistura tres tipos na mesma lista; `spacing` sao os espacos entre
    palavras e viraria uma cue vazia na legenda."""
    response = _response(
        [
            _token("Ola", 0.0, 0.4),
            _token(" ", 0.4, 0.41, type_="spacing"),
            _token("mundo", 0.41, 0.9),
        ]
    )

    result = build_result_from_elevenlabs(response)

    assert [w.text for w in result.words] == ["Ola", "mundo"]


def test_descarta_marcacoes_de_evento_de_audio():
    """`tag_audio_events` fica desligado na requisicao, mas a fronteira nao confia nisso:
    "(risos)" nao e fala e nao pode virar legenda."""
    response = _response(
        [_token("Ola", 0.0, 0.4), _token("(risos)", 0.4, 1.0, type_="audio_event")]
    )

    result = build_result_from_elevenlabs(response)

    assert [w.text for w in result.words] == ["Ola"]


def test_token_sem_timestamp_e_descartado():
    response = _response([_token("Ola", 0.0, 0.4), _token("fantasma", None, None)])

    result = build_result_from_elevenlabs(response)

    assert [w.text for w in result.words] == ["Ola"]


def test_speaker_id_vira_speaker_da_palavra_e_do_segmento():
    response = _response(
        [
            _token("Ola", 0.0, 0.4, speaker_id="speaker_0"),
            _token("tudo", 0.5, 0.9, speaker_id="speaker_0"),
        ]
    )

    result = build_result_from_elevenlabs(response)

    assert result.segments[0].speaker == "speaker_0"
    assert all(w.speaker == "speaker_0" for w in result.words)


def test_duracao_vem_da_resposta():
    response = _response([_token("Ola", 0.0, 0.4)], language_code="pt", audio_duration_secs=12.5)

    result = build_result_from_elevenlabs(response)

    assert result.duration == 12.5


def test_idioma_pedido_vence_o_iso_639_3_da_resposta(tmp_path):
    """O Scribe devolve "por" e os backends locais gravam "pt". O campo vai pro
    transcription.json em cache: o mesmo video nao pode ter idioma diferente conforme o
    backend que rodou."""
    transcriber = _transcriber(
        _response([_token("Ola", 0.0, 0.4)], language_code="por"), language_code="pt"
    )

    result = transcriber.transcribe(_fake_media(tmp_path))

    assert result.language == "pt"


def test_sem_idioma_pedido_reporta_o_que_a_api_detectou(tmp_path):
    transcriber = _transcriber(
        _response([_token("Ola", 0.0, 0.4)], language_code="por"), language_code=None
    )

    result = transcriber.transcribe(_fake_media(tmp_path))

    assert result.language == "por"


def test_word_ids_sao_sequenciais_e_globais():
    response = _response(
        [
            _token("um", 0.0, 0.3, speaker_id="speaker_0"),
            _token("dois", 0.4, 0.7, speaker_id="speaker_1"),
            _token("tres", 0.8, 1.1, speaker_id="speaker_1"),
        ]
    )

    result = build_result_from_elevenlabs(response)

    assert [w.id for w in result.words] == [0, 1, 2]
    assert [s.id for s in result.segments] == [0, 1]


def test_normalizacao_roda_sobre_a_resposta():
    """Mesma passagem dos outros backends: a sigla soletrada chega remontada."""
    response = _response(
        [
            _token("G", 0.0, 0.2),
            _token(".A", 0.2, 0.4),
            _token(".E", 0.4, 0.6),
            _token(".C", 0.6, 0.8),
            _token(".O.", 0.8, 1.0),
        ]
    )

    result = build_result_from_elevenlabs(response)

    assert [w.text for w in result.words] == ["GAECO"]


# --------------------------------------------------------------- segmentacao


def _words(*pairs) -> list[Word]:
    return [
        Word(id=i, text=t, start=s, end=e, speaker=sp)
        for i, (t, s, e, sp) in enumerate(pairs)
    ]


def test_segmento_quebra_na_troca_de_falante():
    words = _words(("um", 0.0, 0.3, "speaker_0"), ("dois", 0.4, 0.7, "speaker_1"))

    segments = split_into_segments(words, SegmentRules())

    assert [s.speaker for s in segments] == ["speaker_0", "speaker_1"]


def test_segmento_quebra_em_silencio_longo():
    words = _words(("um", 0.0, 0.3, None), ("dois", 5.0, 5.3, None))

    segments = split_into_segments(words, SegmentRules(max_gap_seconds=1.0))

    assert len(segments) == 2


def test_segmento_quebra_no_teto_de_duracao():
    """A API devolve palavras, nao paragrafos: sem teto, um monologo de 40 min viraria um
    unico bloco no prompt de selecao, sem estrutura nenhuma."""
    words = _words(*[(f"p{i}", i * 1.0, i * 1.0 + 0.5, None) for i in range(60)])

    segments = split_into_segments(words, SegmentRules(max_seconds=10.0, max_gap_seconds=1.0))

    assert len(segments) > 1
    assert all(s.end - s.start <= 10.0 + 1e-9 for s in segments)


def test_texto_do_segmento_e_a_juncao_das_palavras():
    words = _words(("bom", 0.0, 0.3, None), ("dia", 0.4, 0.7, None))

    (segment,) = split_into_segments(words, SegmentRules())

    assert segment.text == "bom dia"
    assert (segment.start, segment.end) == (0.0, 0.7)


def test_lista_vazia_nao_gera_segmento():
    assert split_into_segments([], SegmentRules()) == []


# --------------------------------------------------------------- keyterms


def test_keyterms_saem_do_vocabulario_da_kb():
    assert valid_keyterms(Vocabulary(terms=("GAECO", "Renan"))) == ["GAECO", "Renan"]


def test_keyterm_longo_demais_e_descartado_na_fronteira():
    """A API recusa a requisicao INTEIRA por causa de um termo invalido; cortar aqui
    troca uma falha total por um termo a menos."""
    assert valid_keyterms(Vocabulary(terms=("ok", "x" * 80))) == ["ok"]


def test_keyterm_com_palavras_demais_e_descartado():
    assert valid_keyterms(Vocabulary(terms=("uma frase inteira bem longa aqui",))) == []


def test_keyterms_sao_limitados_a_cem():
    vocabulario = Vocabulary(terms=tuple(f"Termo{i}" for i in range(300)))

    assert len(valid_keyterms(vocabulario)) == 100


# --------------------------------------------------------------- requisicao


def test_requisicao_usa_o_modelo_scribe_v2_e_desliga_eventos_de_audio(tmp_path):
    transcriber = _transcriber(_response([_token("Ola", 0.0, 0.4)]))

    transcriber.transcribe(_fake_media(tmp_path))

    (call,) = transcriber._client.calls
    assert call["model_id"] == MODEL_ID
    assert call["tag_audio_events"] is False
    assert call["timestamps_granularity"] == "word"


def test_requisicao_repassa_idioma_diarizacao_e_keyterms(tmp_path):
    transcriber = _transcriber(
        _response([_token("Ola", 0.0, 0.4)]),
        language_code="pt",
        diarize=True,
        vocabulary=Vocabulary(terms=("GAECO",)),
    )

    transcriber.transcribe(_fake_media(tmp_path))

    (call,) = transcriber._client.calls
    assert call["language_code"] == "pt"
    assert call["diarize"] is True
    assert call["keyterms"] == ["GAECO"]


def test_no_verbatim_vem_ligado_por_padrao(tmp_path):
    """Medido no video de teste: sem isso o "Ponto:" que o narrador dita ao ler uma lista
    e queimado na legenda como a palavra "Ponto", numero fica por extenso e gagueira vira
    token de lixo."""
    transcriber = _transcriber(_response([_token("Ola", 0.0, 0.4)]))

    transcriber.transcribe(_fake_media(tmp_path))

    assert transcriber._client.calls[0]["no_verbatim"] is True


def test_no_verbatim_pode_ser_desligado(tmp_path):
    transcriber = _transcriber(_response([_token("Ola", 0.0, 0.4)]), no_verbatim=False)

    transcriber.transcribe(_fake_media(tmp_path))

    assert transcriber._client.calls[0]["no_verbatim"] is False


def test_vocabulario_vazio_nao_manda_keyterms(tmp_path):
    transcriber = _transcriber(_response([_token("Ola", 0.0, 0.4)]))

    transcriber.transcribe(_fake_media(tmp_path))

    assert "keyterms" not in transcriber._client.calls[0]


def test_granularidade_invalida_falha_na_construcao():
    with pytest.raises(ValueError, match="timestamps_granularity invalido"):
        ElevenLabsTranscriber(timestamps_granularity="frase", client_factory=lambda: None)


def test_extra_nao_instalado_tem_mensagem_propria(monkeypatch, tmp_path):
    """Chave presente mas SDK ausente e a outra falha de configuracao, com correcao
    diferente da chave faltando."""
    import builtins

    real_import = builtins.__import__

    def sem_elevenlabs(name, *args, **kwargs):
        if name.startswith("elevenlabs"):
            raise ImportError("No module named 'elevenlabs'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sem_elevenlabs)
    transcriber = ElevenLabsTranscriber(api_key="chave-valida")

    with pytest.raises(TranscriptionError, match="cloud-transcribe"):
        transcriber.transcribe(_fake_media(tmp_path))


def test_sem_api_key_a_mensagem_diz_onde_pegar_a_chave(tmp_path):
    """Chave ausente e extra nao instalado sao falhas diferentes: a mensagem tem que
    apontar a correcao certa mesmo sem a SDK instalada na maquina."""
    transcriber = ElevenLabsTranscriber(api_key=None)

    with pytest.raises(TranscriptionError, match="ELEVENLABS_API_KEY"):
        transcriber.transcribe(_fake_media(tmp_path))


# --------------------------------------------------------------- extracao de audio


def test_needs_extraction_reconhece_audio_ja_comprimido():
    assert needs_extraction("video.mp4") is True
    assert needs_extraction("audio.ogg") is False
    assert needs_extraction("AUDIO.MP3") is False


def test_extract_audio_descarta_video_e_forca_mono_16k(tmp_path):
    """Subir 2GB de video em vez de 14MB de audio domina o tempo da etapa em nuvem."""
    calls = []
    target = tmp_path / "out" / "audio.ogg"

    extract_audio(tmp_path / "video.mp4", target, runner=lambda cmd, **kw: calls.append(cmd))

    (cmd,) = calls
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-c:a") + 1] == "libopus"
    assert target.parent.exists()


def test_transcribe_extrai_o_audio_antes_de_subir(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    extraidos = []

    def fake_extractor(source, output, **kwargs):
        extraidos.append((Path(source), Path(output)))
        Path(output).write_bytes(b"audio")
        return Path(output)

    transcriber = ElevenLabsTranscriber(
        client_factory=lambda: FakeClient(_response([_token("Ola", 0.0, 0.4)])),
        extract_audio_first=True,
        audio_extractor=fake_extractor,
    )
    transcriber.transcribe(video)

    assert len(extraidos) == 1
    assert extraidos[0][0] == video
    assert extraidos[0][1].suffix == ".ogg"


def test_transcribe_nao_extrai_quando_a_entrada_ja_e_audio(tmp_path):
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"audio")
    extraidos = []

    transcriber = ElevenLabsTranscriber(
        client_factory=lambda: FakeClient(_response([_token("Ola", 0.0, 0.4)])),
        extract_audio_first=True,
        audio_extractor=lambda *a, **k: extraidos.append(a),
    )
    transcriber.transcribe(audio)

    assert extraidos == []


def test_audio_path_da_transcricao_aponta_para_a_entrada_original(tmp_path):
    """O `audio_path` e consumido pela prosodia e pelo active speaker, que precisam do
    arquivo do pipeline, nao do temporario que foi subido e apagado."""
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"audio")
    transcriber = ElevenLabsTranscriber(
        client_factory=lambda: FakeClient(_response([_token("Ola", 0.0, 0.4)])),
        extract_audio_first=True,
    )

    result = transcriber.transcribe(audio)

    assert result.audio_path == str(audio)


# --------------------------------------------------------------- fabrica


def test_fabrica_constroi_o_backend_elevenlabs():
    transcriber = build_transcriber(
        TranscriberSettings(backend="elevenlabs", elevenlabs_api_key="chave-de-teste")
    )

    assert isinstance(transcriber, ElevenLabsTranscriber)
    assert transcriber.api_key == "chave-de-teste"


def test_fabrica_cai_para_a_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "do-ambiente")

    transcriber = build_transcriber(TranscriberSettings(backend="elevenlabs"))

    assert transcriber.api_key == "do-ambiente"


def test_fabrica_repassa_vocabulario_e_diarizacao():
    vocabulario = Vocabulary(terms=("GAECO",))

    transcriber = build_transcriber(
        TranscriberSettings(backend="elevenlabs", diarize=True, elevenlabs_api_key="k"),
        vocabulary=vocabulario,
    )

    assert transcriber.vocabulary is vocabulario
    assert transcriber.diarize is True


# --------------------------------------------------------------- timeout


def test_timeout_escala_com_a_duracao_do_audio(monkeypatch, tmp_path):
    """O endpoint e sincrono e o default de 240s da SDK estoura em video longo: medido
    com um video de 81min, que falhou com httpx.ReadTimeout antes de qualquer resposta."""
    monkeypatch.setattr(
        elevenlabs_transcriber, "probe_duration_seconds", lambda path: 4904.0
    )
    transcriber = ElevenLabsTranscriber(api_key="k")

    assert transcriber._timeout_for(tmp_path / "audio.ogg") == 2452.0


def test_timeout_tem_piso_para_audio_curto(monkeypatch, tmp_path):
    monkeypatch.setattr(elevenlabs_transcriber, "probe_duration_seconds", lambda path: 60.0)
    transcriber = ElevenLabsTranscriber(api_key="k")

    assert transcriber._timeout_for(tmp_path / "audio.ogg") == MIN_TIMEOUT_SECONDS


def test_timeout_sem_duracao_conhecida_usa_o_pior_caso(monkeypatch, tmp_path):
    monkeypatch.setattr(elevenlabs_transcriber, "probe_duration_seconds", lambda path: None)
    transcriber = ElevenLabsTranscriber(api_key="k")

    assert transcriber._timeout_for(tmp_path / "audio.ogg") == FALLBACK_TIMEOUT_SECONDS


def test_timeout_sobrevive_a_ffprobe_quebrado(monkeypatch, tmp_path, caplog):
    def explode(path):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(elevenlabs_transcriber, "probe_duration_seconds", explode)
    transcriber = ElevenLabsTranscriber(api_key="k")

    with caplog.at_level("WARNING"):
        assert transcriber._timeout_for(tmp_path / "audio.ogg") == FALLBACK_TIMEOUT_SECONDS
    assert "duracao" in caplog.text


def test_timeout_explicito_vence_o_calculo(tmp_path):
    transcriber = ElevenLabsTranscriber(api_key="k", timeout_seconds=99.0)

    assert transcriber._timeout_for(tmp_path / "audio.ogg") == 99.0


def test_timeout_vai_na_requisicao(tmp_path):
    transcriber = _transcriber(_response([_token("Ola", 0.0, 0.4)]), timeout_seconds=777.0)

    transcriber.transcribe(_fake_media(tmp_path))

    assert transcriber._client.calls[0]["request_options"] == {"timeout_in_seconds": 777}
