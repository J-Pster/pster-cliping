import io
import logging
from types import SimpleNamespace

import pytest
from PIL import Image

from clipador.thumbnail.ai_thumbnail import AIThumbnailGenerator
from clipador.thumbnail.face_library import PoliticalFigure
from clipador.thumbnail.models import ThumbnailError


def base_frame(color=(120, 120, 120)) -> Image.Image:
    return Image.new("RGB", (64, 48), color=color)


def response_with(image: Image.Image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    part = SimpleNamespace(inline_data=SimpleNamespace(data=buffer.getvalue()))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
    )


class FakeChat:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.messages: list[list] = []

    def send_message(self, contents):
        self.messages.append(contents)
        if self._error is not None:
            raise self._error
        return self._response


class FakeGeminiClient:
    def __init__(self, response=None, error=None):
        self._chat = FakeChat(response=response, error=error)
        self.chats = SimpleNamespace(create=lambda **kwargs: self._chat)


# --- available -----------------------------------------------------------------


def test_available_false_sem_gemini_api_key(monkeypatch, caplog):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with caplog.at_level(logging.WARNING):
        generator = AIThumbnailGenerator()
        assert generator.available is False

    assert any("GEMINI_API_KEY" in record.getMessage() for record in caplog.records)


def test_available_true_com_client_factory_injetado(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    generator = AIThumbnailGenerator(
        client_factory=lambda: FakeGeminiClient(), face_reference_dir=None
    )

    assert generator.available is True


# --- generate --------------------------------------------------------------------


def test_generate_sem_headline_levanta_erro_sem_chamar_a_api():
    client = FakeGeminiClient(response=response_with(base_frame()))
    generator = AIThumbnailGenerator(client_factory=lambda: client, face_reference_dir=None)

    with pytest.raises(ThumbnailError):
        generator.generate(base_frame(), "")
    assert client._chat.messages == []


def test_generate_indisponivel_levanta_erro(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    generator = AIThumbnailGenerator(face_reference_dir=None)

    with pytest.raises(ThumbnailError, match="GEMINI_API_KEY"):
        generator.generate(base_frame(), "GANCHO")


def test_generate_com_client_fake_devolve_a_imagem_gerada():
    gerado = Image.new("RGB", (80, 140), color=(9, 9, 200))
    client = FakeGeminiClient(response=response_with(gerado))
    generator = AIThumbnailGenerator(client_factory=lambda: client, face_reference_dir=None)

    result = generator.generate(base_frame(), "gancho curto", aspect_ratio="9:16")

    assert result.size == (80, 140)
    assert result.getpixel((0, 0)) == (9, 9, 200)
    prompt = client._chat.messages[0][0]
    assert "GANCHO CURTO" in prompt
    assert "9:16" in prompt


def test_generate_quando_a_api_falha_levanta_erro(caplog):
    client = FakeGeminiClient(error=RuntimeError("modelo em alta demanda"))
    generator = AIThumbnailGenerator(client_factory=lambda: client, face_reference_dir=None)

    with pytest.raises(ThumbnailError, match="modelo em alta demanda"):
        generator.generate(base_frame(), "GANCHO")


def test_generate_quando_resposta_sem_imagem_levanta_erro(caplog):
    resposta_vazia = SimpleNamespace(candidates=[])
    client = FakeGeminiClient(response=resposta_vazia)
    generator = AIThumbnailGenerator(client_factory=lambda: client, face_reference_dir=None)

    with pytest.raises(ThumbnailError, match="sem imagem"):
        generator.generate(base_frame(), "GANCHO")


# --- _load_face_references ------------------------------------------------------


def _save_fake_photos(dir_path, names) -> list:
    paths = []
    for name in names:
        path = dir_path / name
        Image.new("RGB", (10, 10), color=(200, 100, 50)).save(path)
        paths.append(path)
    return paths


def test_load_face_references_carrega_todas_ordenadas_e_usa_cache(tmp_path):
    _save_fake_photos(tmp_path, ["b.png", "a.jpg", "c.jpeg"])
    generator = AIThumbnailGenerator(face_reference_dir=tmp_path)

    imagens = generator._load_face_references()

    assert len(imagens) == 3
    assert all(isinstance(img, Image.Image) for img in imagens)

    # apaga os arquivos do disco: se a segunda chamada devolver as mesmas imagens,
    # o cache em memoria esta funcionando (nao reabriu do disco).
    for path in tmp_path.iterdir():
        path.unlink()

    imagens_cacheadas = generator._load_face_references()
    assert imagens_cacheadas == imagens
    assert len(imagens_cacheadas) == 3


def test_load_face_references_dir_none_devolve_lista_vazia():
    generator = AIThumbnailGenerator(face_reference_dir=None)

    assert generator._load_face_references() == []


def test_load_face_references_dir_inexistente_devolve_lista_vazia(tmp_path):
    generator = AIThumbnailGenerator(face_reference_dir=tmp_path / "nao_existe")

    assert generator._load_face_references() == []


def test_load_face_references_pula_arquivo_corrompido(tmp_path, caplog):
    _save_fake_photos(tmp_path, ["boa_01.png", "boa_02.png"])
    (tmp_path / "corrompida.png").write_bytes(b"isso nao e uma imagem valida")

    generator = AIThumbnailGenerator(face_reference_dir=tmp_path)

    with caplog.at_level(logging.WARNING):
        imagens = generator._load_face_references()

    assert len(imagens) == 2
    assert any("corrompida.png" in record.getMessage() for record in caplog.records)


# --- generate com face reference -------------------------------------------------


def test_generate_com_face_reference_dir_anexa_fotos_e_ajusta_prompt(tmp_path):
    _save_fake_photos(tmp_path, ["renan_01.png", "renan_02.png"])
    client = FakeGeminiClient(response=response_with(base_frame()))
    generator = AIThumbnailGenerator(
        client_factory=lambda: client,
        face_reference_dir=tmp_path,
        face_reference_person="Renan Santos",
    )

    generator.generate(base_frame(), "GANCHO")

    contents = client._chat.messages[0]
    prompt = contents[0]
    assert len(contents) == 4  # prompt + frame + 2 fotos de referencia
    assert isinstance(contents[2], Image.Image)
    assert isinstance(contents[3], Image.Image)

    from clipador.thumbnail.ai_thumbnail import FACE_REFERENCE_INSTRUCTION_TEMPLATE

    esperado = FACE_REFERENCE_INSTRUCTION_TEMPLATE.format(count=2, person_name="Renan Santos")
    assert esperado in prompt
    assert "2 additional" in prompt


def test_generate_sem_face_reference_dir_mantem_comportamento_antigo():
    client = FakeGeminiClient(response=response_with(base_frame()))
    generator = AIThumbnailGenerator(client_factory=lambda: client, face_reference_dir=None)

    generator.generate(base_frame(), "GANCHO")

    contents = client._chat.messages[0]
    assert len(contents) == 2
    prompt = contents[0]
    assert "Face reference library" not in prompt


# --- generate com `subject` (escolha POR CLIPE, ver thumbnail.subject) -----------


def test_generate_subject_sobrescreve_o_default_da_instancia(tmp_path):
    """O `subject` escolhido por clipe manda mais que o default fixo da instancia - e o
    que corrige o defeito relatado: um clipe sobre outra pessoa nao pode herdar a
    referencia facial de quem a instancia foi construida com."""
    default_dir = tmp_path / "default_person"
    default_dir.mkdir()
    _save_fake_photos(default_dir, ["default_01.png"])

    subject_dir = tmp_path / "lula"
    subject_dir.mkdir()
    _save_fake_photos(subject_dir, ["lula_01.png", "lula_02.png"])
    subject = PoliticalFigure("lula", "Luiz Inácio Lula da Silva", subject_dir)

    client = FakeGeminiClient(response=response_with(base_frame()))
    generator = AIThumbnailGenerator(
        client_factory=lambda: client,
        face_reference_dir=default_dir,
        face_reference_person="Default Person",
    )

    generator.generate(base_frame(), "GANCHO", subject=subject)

    contents = client._chat.messages[0]
    prompt = contents[0]
    assert len(contents) == 4  # prompt + frame + 2 fotos do Lula (nao 1 do default)
    assert "Luiz Inácio Lula da Silva" in prompt
    assert "Default Person" not in prompt


def test_generate_sem_subject_cai_pro_default_da_instancia(tmp_path):
    default_dir = tmp_path / "default_person"
    default_dir.mkdir()
    _save_fake_photos(default_dir, ["default_01.png"])

    client = FakeGeminiClient(response=response_with(base_frame()))
    generator = AIThumbnailGenerator(
        client_factory=lambda: client,
        face_reference_dir=default_dir,
        face_reference_person="Default Person",
    )

    generator.generate(base_frame(), "GANCHO", subject=None)

    prompt = client._chat.messages[0][0]
    assert "Default Person" in prompt


def test_generate_subject_sem_default_da_instancia_ainda_anexa_a_foto_certa(tmp_path):
    subject_dir = tmp_path / "lula"
    subject_dir.mkdir()
    _save_fake_photos(subject_dir, ["lula_01.png"])
    subject = PoliticalFigure("lula", "Lula", subject_dir)

    client = FakeGeminiClient(response=response_with(base_frame()))
    generator = AIThumbnailGenerator(client_factory=lambda: client, face_reference_dir=None)

    generator.generate(base_frame(), "GANCHO", subject=subject)

    contents = client._chat.messages[0]
    assert len(contents) == 3  # prompt + frame + 1 foto do Lula
    assert "Lula" in contents[0]


def test_load_face_references_cache_e_por_diretorio_nao_conflita_entre_subjects(tmp_path):
    """Clipes diferentes do mesmo run podem escolher `subject` diferentes - o cache tem
    que ser por diretorio, senao o segundo subject herdaria as fotos do primeiro."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    _save_fake_photos(dir_a, ["a_01.png"])
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    _save_fake_photos(dir_b, ["b_01.png", "b_02.png"])

    generator = AIThumbnailGenerator(face_reference_dir=None)

    assert len(generator._load_face_references(dir_a)) == 1
    assert len(generator._load_face_references(dir_b)) == 2
    # repete na ordem inversa: cada dir continua devolvendo a contagem certa (cache nao
    # misturou os dois diretorios).
    assert len(generator._load_face_references(dir_b)) == 2
    assert len(generator._load_face_references(dir_a)) == 1
