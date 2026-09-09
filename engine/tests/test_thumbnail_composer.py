import logging

import pytest
from PIL import Image

from clipador.reframe.models import FaceBox
from clipador.thumbnail import ThumbnailComposer, ThumbnailStyle
from clipador.thumbnail.face_library import PoliticalFigure
from clipador.thumbnail.models import ThumbnailError

SIZE = (320, 180)
ACCENT = (255, 0, 255)
FACE = FaceBox(x=120.0, y=40.0, width=80.0, height=80.0, confidence=0.9)


class FakeFaceDetector:
    def __init__(self, faces):
        self._faces = faces

    def detect_faces(self, frame):
        return self._faces


class FakeCutout:
    def __init__(self, person=None, error=None):
        self._person = person
        self._error = error
        self.calls = []

    def cut(self, frame_path):
        self.calls.append(frame_path)
        if self._error is not None:
            raise self._error
        return self._person


class FakeBackgroundEditor:
    def __init__(self, treated=None, error=None):
        self._treated = treated
        self._error = error

    def edit(self, frame, prompt=None):
        if self._error is not None:
            raise self._error
        return self._treated or Image.new("RGB", frame.size, color=(30, 30, 30))


class FakeAIGenerator:
    """Espelha o contrato real de `AIThumbnailGenerator.generate`: nunca devolve None,
    ou devolve a imagem ou levanta. Por padrao (sem `image=`) simula indisponibilidade
    levantando `ThumbnailError`, como o real faz sem GEMINI_API_KEY. Testes de
    `compose_layered()` nem chegam a usar isto; testes do caminho de IA injetam
    `image=` explicito."""

    def __init__(self, image=None, error=None):
        self._image = image
        self._error = error
        self.calls: list[tuple[str, str]] = []
        self.last_subject = "unset"

    def generate(self, frame, headline, aspect_ratio="9:16", subject=None):
        self.calls.append((headline, aspect_ratio))
        self.last_subject = subject
        if self._error is not None:
            raise self._error
        if self._image is None:
            raise ThumbnailError("simulado: IA indisponivel/sem imagem")
        return self._image


def write_frame(tmp_path, color=(90, 90, 90)):
    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", SIZE, color=color).save(frame_path)
    return frame_path


def build_composer(
    faces=(FACE,), cutout=None, background=None, ai_generator=None, **style_kwargs
):
    style = ThumbnailStyle(accent_color=ACCENT, **style_kwargs)
    return ThumbnailComposer(
        cutout=cutout or FakeCutout(person=None),
        background_editor=background or FakeBackgroundEditor(),
        face_detector=FakeFaceDetector(list(faces)),
        style=style,
        ai_generator=ai_generator or FakeAIGenerator(),
    )


def accent_pixels(image: Image.Image) -> int:
    return sum(1 for pixel in image.convert("RGB").get_flattened_data() if pixel == ACCENT)


def meio_vertical() -> int:
    return SIZE[1] // 2


def test_compose_layered_monta_imagem_final_do_tamanho_do_frame(tmp_path):
    person = Image.new("RGBA", SIZE, color=(200, 10, 10, 255))
    composer = build_composer(cutout=FakeCutout(person=person))

    result = composer.compose_layered(write_frame(tmp_path), "OLHA ISSO")

    assert result.size == SIZE
    assert result.mode == "RGB"


def test_compose_layered_cola_o_recorte_da_pessoa_por_cima_do_fundo_tratado(tmp_path):
    person = Image.new("RGBA", SIZE, color=(200, 10, 10, 255))
    cutout = FakeCutout(person=person)
    composer = build_composer(cutout=cutout, faces=())

    result = composer.compose_layered(write_frame(tmp_path), "")

    assert cutout.calls
    assert result.getpixel((0, 0)) == (200, 10, 10)


def test_compose_layered_sem_recorte_disponivel_ainda_produz_imagem_valida(tmp_path):
    composer = build_composer(cutout=FakeCutout(person=None), faces=())

    result = composer.compose_layered(write_frame(tmp_path), "")

    # Fundo tratado do FakeBackgroundEditor, sem nenhuma colagem por cima.
    assert result.size == SIZE
    assert result.getpixel((0, 0)) == (30, 30, 30)


def test_compose_layered_sem_rosto_detectado_nao_desenha_seta(tmp_path):
    com_rosto = build_composer(faces=(FACE,)).compose_layered(write_frame(tmp_path), "")
    sem_rosto = build_composer(faces=()).compose_layered(write_frame(tmp_path), "")

    assert accent_pixels(com_rosto) > 0
    assert accent_pixels(sem_rosto) == 0


def test_compose_layered_com_highlight_none_nao_desenha_destaque(tmp_path):
    composer = build_composer(faces=(FACE,), highlight=None)

    result = composer.compose_layered(write_frame(tmp_path), "")

    assert accent_pixels(result) == 0


def test_compose_layered_escreve_a_headline_por_cima(tmp_path):
    sem_texto = build_composer(faces=()).compose_layered(write_frame(tmp_path), "")
    com_texto = build_composer(faces=()).compose_layered(write_frame(tmp_path), "sera mesmo")

    assert list(com_texto.get_flattened_data()) != list(sem_texto.get_flattened_data())


def test_compose_layered_posiciona_a_headline_no_lado_com_mais_espaco_livre(tmp_path):
    """Rosto no topo empurra a manchete pra base, e vice-versa: o texto nunca cobre o rosto."""
    face_no_topo = FaceBox(x=120.0, y=10.0, width=60.0, height=50.0, confidence=0.9)
    face_na_base = FaceBox(x=120.0, y=120.0, width=60.0, height=50.0, confidence=0.9)
    topo = build_composer(faces=(face_no_topo,), highlight=None).compose_layered(
        write_frame(tmp_path), "OPA"
    )
    base = build_composer(faces=(face_na_base,), highlight=None).compose_layered(
        write_frame(tmp_path), "OPA"
    )

    def linhas_com_texto(image):
        pixels = image.load()
        return {
            y
            for y in range(image.height)
            for x in range(image.width)
            if pixels[x, y] != (30, 30, 30)
        }

    assert max(linhas_com_texto(topo)) > meio_vertical()
    assert min(linhas_com_texto(base)) < meio_vertical()


def test_compose_layered_nao_propaga_erro_de_sub_etapa_e_ainda_devolve_imagem(tmp_path, caplog):
    composer = build_composer(
        cutout=FakeCutout(error=RuntimeError("recorte explodiu")),
        background=FakeBackgroundEditor(error=RuntimeError("fundo explodiu")),
    )

    with caplog.at_level(logging.WARNING):
        result = composer.compose_layered(write_frame(tmp_path), "GANCHO")

    assert result.size == SIZE
    mensagens = " ".join(record.getMessage() for record in caplog.records)
    assert "recorte explodiu" in mensagens
    assert "fundo explodiu" in mensagens


# --- geracao completa via IA (caminho preferido) ------------------------------


def test_compose_usa_a_geracao_completa_da_ia_quando_disponivel(tmp_path):
    gerado = Image.new("RGB", (99, 199), color=(1, 2, 3))
    ai_generator = FakeAIGenerator(image=gerado)
    cutout = FakeCutout(person=None)
    background = FakeBackgroundEditor()
    composer = build_composer(cutout=cutout, background=background, ai_generator=ai_generator)

    result = composer.compose(write_frame(tmp_path), "GANCHO", aspect_ratio="16:9")

    assert result.size == (99, 199)
    assert result.getpixel((0, 0)) == (1, 2, 3)
    assert ai_generator.calls == [("GANCHO", "16:9")]
    # pipeline em camadas nao deve nem rodar quando a IA ja devolveu a thumbnail pronta.
    assert not cutout.calls


def test_compose_repassa_subject_pro_ai_generator(tmp_path):
    subject = PoliticalFigure("lula", "Lula", tmp_path / "lula_fotos")
    ai_generator = FakeAIGenerator(image=Image.new("RGB", (10, 10)))
    composer = build_composer(ai_generator=ai_generator)

    composer.compose(write_frame(tmp_path), "GANCHO", subject=subject)

    assert ai_generator.last_subject is subject


def test_compose_sem_subject_repassa_none(tmp_path):
    ai_generator = FakeAIGenerator(image=Image.new("RGB", (10, 10)))
    composer = build_composer(ai_generator=ai_generator)

    composer.compose(write_frame(tmp_path), "GANCHO")

    assert ai_generator.last_subject is None


def test_compose_ai_generator_indisponivel_levanta_erro_sem_fallback(tmp_path):
    """Decisao do projeto: sem Gemini disponivel, `compose()` nao degrada em silencio
    pra composicao em camadas, levanta erro (ver topo do modulo)."""
    composer = build_composer(ai_generator=FakeAIGenerator(image=None), faces=())

    with pytest.raises(ThumbnailError):
        composer.compose(write_frame(tmp_path), "", aspect_ratio="9:16")


def test_compose_ai_generator_que_falha_levanta_erro_sem_fallback(tmp_path):
    ai_generator = FakeAIGenerator(error=RuntimeError("gemini explodiu"))
    composer = build_composer(ai_generator=ai_generator)

    with pytest.raises(RuntimeError, match="gemini explodiu"):
        composer.compose(write_frame(tmp_path), "GANCHO")


def test_compose_layered_com_face_detector_que_explode_segue_sem_rosto(tmp_path):
    class ExplodingDetector:
        def detect_faces(self, frame):
            raise RuntimeError("modelo de rosto ausente")

    composer = ThumbnailComposer(
        cutout=FakeCutout(person=None),
        background_editor=FakeBackgroundEditor(),
        face_detector=ExplodingDetector(),
        style=ThumbnailStyle(accent_color=ACCENT),
        ai_generator=FakeAIGenerator(),
    )

    result = composer.compose_layered(write_frame(tmp_path), "GANCHO")

    assert result.size == SIZE
    assert accent_pixels(result) == 0
