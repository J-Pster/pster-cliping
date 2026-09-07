import io
import logging
import sys
import types

from PIL import Image

from clipador.thumbnail import PersonCutout


def png_bytes(size=(40, 30), color=(10, 20, 30, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def write_frame(tmp_path):
    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", (40, 30), color=(200, 100, 50)).save(frame_path)
    return frame_path


def test_available_true_quando_rembg_importa(monkeypatch):
    stub = types.ModuleType("rembg")
    stub.remove = staticmethod(lambda data: png_bytes())
    monkeypatch.setitem(sys.modules, "rembg", stub)

    assert PersonCutout().available is True


def test_available_false_quando_rembg_nao_importa(monkeypatch):
    monkeypatch.setitem(sys.modules, "rembg", None)

    assert PersonCutout().available is False


def test_cut_com_remove_fn_injetado_devolve_imagem_rgba(tmp_path):
    frame_path = write_frame(tmp_path)
    recebido = {}

    def fake_remove(data):
        recebido["data"] = data
        return png_bytes()

    result = PersonCutout(remove_fn=fake_remove).cut(frame_path)

    assert recebido["data"] == frame_path.read_bytes()
    assert result.mode == "RGBA"
    assert result.size == (40, 30)


def test_cut_com_remove_fn_que_explode_devolve_none_sem_propagar(tmp_path, caplog):
    frame_path = write_frame(tmp_path)

    def exploding_remove(data):
        raise RuntimeError("modelo do rembg corrompido")

    with caplog.at_level(logging.WARNING):
        result = PersonCutout(remove_fn=exploding_remove).cut(frame_path)

    assert result is None
    assert any("modelo do rembg corrompido" in record.getMessage() for record in caplog.records)


def test_cut_sem_rembg_disponivel_devolve_none(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "rembg", None)

    assert PersonCutout().cut(write_frame(tmp_path)) is None
