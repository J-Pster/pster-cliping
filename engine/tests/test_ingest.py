import pytest

from clipador.ingest import IngestError, SourceKind, extract_video_id, resolve_source

VIDEO_ID = "T3ENScVymJQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42s",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=abc",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"  https://www.youtube.com/embed/{VIDEO_ID}  ",
    ],
)
def test_resolve_source_roteia_url_do_youtube(url):
    source = resolve_source(url)

    assert source.kind is SourceKind.YOUTUBE_URL
    assert source.video_id == VIDEO_ID
    assert source.needs_download is True
    assert source.path is None


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/123456789",
        "https://www.youtube.com/watch?v=curto",
        "https://www.youtube.com/@canal",
        "ftp://youtu.be/T3ENScVymJQ",
        "youtube.com/watch?v=T3ENScVymJQ",
    ],
)
def test_extract_video_id_rejeita_entradas_invalidas(url):
    assert extract_video_id(url) is None


def test_resolve_source_roteia_arquivo_local(tmp_path):
    video = tmp_path / "master.mp4"
    video.write_bytes(b"fake")

    source = resolve_source(str(video))

    assert source.kind is SourceKind.LOCAL_FILE
    assert source.needs_download is False
    assert source.path == video.resolve()
    assert source.video_id is None


def test_resolve_source_falha_para_diretorio(tmp_path):
    with pytest.raises(IngestError, match="nao e um arquivo"):
        resolve_source(str(tmp_path))


def test_resolve_source_falha_para_entrada_desconhecida(tmp_path):
    with pytest.raises(IngestError):
        resolve_source(str(tmp_path / "nao-existe.mp4"))


def test_resolve_source_falha_para_entrada_vazia():
    with pytest.raises(IngestError, match="vazia"):
        resolve_source("   ")
