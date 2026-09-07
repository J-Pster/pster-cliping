import io
import logging
from types import SimpleNamespace

from PIL import Image

from clipador.thumbnail import GeminiBackgroundEditor, fallback_treatment


def base_frame(color=(120, 120, 120)) -> Image.Image:
    return Image.new("RGB", (64, 48), color=color)


def response_with(image: Image.Image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    part = SimpleNamespace(inline_data=SimpleNamespace(data=buffer.getvalue()))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
    )


class FakeModels:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeGeminiClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response=response, error=error)


# --- available ---------------------------------------------------------------


def test_available_false_sem_gemini_api_key(monkeypatch, caplog):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with caplog.at_level(logging.WARNING):
        editor = GeminiBackgroundEditor()
        assert editor.available is False

    assert any("GEMINI_API_KEY" in record.getMessage() for record in caplog.records)


def test_available_true_com_client_factory_injetado(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    editor = GeminiBackgroundEditor(client_factory=lambda: FakeGeminiClient())

    assert editor.available is True


# --- edit --------------------------------------------------------------------


def test_edit_com_client_fake_devolve_a_imagem_editada():
    edited = Image.new("RGB", (64, 48), color=(10, 200, 10))
    client = FakeGeminiClient(response=response_with(edited))
    editor = GeminiBackgroundEditor(client_factory=lambda: client)

    result = editor.edit(base_frame())

    assert result.size == (64, 48)
    assert result.getpixel((0, 0)) == (10, 200, 10)
    assert "rosto" in client.models.calls[0]["contents"][0].lower()


def test_edit_quando_a_api_falha_cai_no_fallback_local(caplog):
    frame = base_frame()
    editor = GeminiBackgroundEditor(
        client_factory=lambda: FakeGeminiClient(error=RuntimeError("quota estourada"))
    )

    with caplog.at_level(logging.WARNING):
        result = editor.edit(frame)

    assert list(result.get_flattened_data()) == list(fallback_treatment(frame).get_flattened_data())
    assert any("quota estourada" in record.getMessage() for record in caplog.records)


def test_edit_sem_chave_nem_lib_cai_no_fallback_sem_levantar(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    frame = base_frame()

    result = GeminiBackgroundEditor().edit(frame)

    assert list(result.get_flattened_data()) == list(fallback_treatment(frame).get_flattened_data())


# --- fallback_treatment -------------------------------------------------------


def test_fallback_treatment_mantem_o_tamanho_e_realmente_trata_a_imagem():
    frame = Image.new("RGB", (32, 24), color=(200, 180, 160))
    frame.paste(Image.new("RGB", (8, 8), color=(0, 0, 255)), (4, 4))

    treated = fallback_treatment(frame)

    assert treated.size == frame.size
    assert treated.mode == "RGB"
    assert list(treated.get_flattened_data()) != list(frame.get_flattened_data())
    # Escurecido: a media de luminancia cai depois do tratamento.
    assert sum(sum(p) for p in treated.get_flattened_data()) < sum(sum(p) for p in frame.get_flattened_data())
