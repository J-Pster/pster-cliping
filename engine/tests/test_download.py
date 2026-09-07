import json

import pytest

from clipador.download import (
    DownloadError,
    MetadataError,
    YouTubeMetadataFetcher,
    YtDlpDownloader,
    extract_chapters,
    load_info_json,
    pick_thumbnail,
)

INFO_JSON = {
    "id": "T3ENScVymJQ",
    "title": "Live do Missao",
    "duration": 2820,
    "chapters": [
        {"title": "Abertura", "start_time": 0.0, "end_time": 120.5},
        {"title": "Pauta economica", "start_time": 120.5, "end_time": 900.0},
    ],
}


class FakeYdl:
    def __init__(self, opts, info, filename="ignorado.mp4"):
        self.opts = opts
        self.calls = []
        self._info = info
        self._filename = filename

    def extract_info(self, url, download):
        self.calls.append((url, download))
        return self._info

    def prepare_filename(self, info):
        return self._filename


def _factory(info, filename="ignorado.mp4"):
    holder = {}

    def factory(opts):
        holder["ydl"] = FakeYdl(opts, info, filename)
        return holder["ydl"]

    return factory, holder


def test_extract_chapters_ordena_e_ignora_entradas_invalidas():
    info = {
        "chapters": [
            {"title": "Segundo", "start_time": 100},
            {"title": "Primeiro", "start_time": 0, "end_time": 100},
            {"title": "Sem inicio"},
            "lixo",
        ]
    }

    chapters = extract_chapters(info)

    assert [c.title for c in chapters] == ["Primeiro", "Segundo"]
    assert chapters[0].duration == 100.0
    assert chapters[1].end is None
    assert chapters[1].duration is None


def test_extract_chapters_sem_capitulos():
    assert extract_chapters({}) == ()
    assert extract_chapters(None) == ()


def test_load_info_json(tmp_path):
    path = tmp_path / "video.info.json"
    path.write_text(json.dumps(INFO_JSON), encoding="utf-8")

    assert load_info_json(path)["id"] == "T3ENScVymJQ"


def test_build_options_configura_merge_e_info_json(tmp_path):
    opts = YtDlpDownloader(tmp_path, merge_output_format="mkv").build_options()

    assert opts["merge_output_format"] == "mkv"
    assert opts["writeinfojson"] is True
    assert opts["format"] == "bestvideo*+bestaudio/best"
    assert opts["noplaylist"] is True
    assert str(tmp_path) in opts["outtmpl"]
    assert "cookiesfrombrowser" not in opts


def test_build_options_sem_cookies_from_browser_por_padrao(tmp_path):
    opts = YtDlpDownloader(tmp_path).build_options()
    assert "cookiesfrombrowser" not in opts


def test_build_options_cookies_from_browser_vira_tupla_de_1(tmp_path):
    opts = YtDlpDownloader(tmp_path, cookies_from_browser="firefox").build_options()
    assert opts["cookiesfrombrowser"] == ("firefox",)


def test_download_usa_filepath_do_requested_download(tmp_path):
    video_path = tmp_path / "T3ENScVymJQ.mp4"
    info = dict(INFO_JSON, requested_downloads=[{"filepath": str(video_path)}])
    (tmp_path / "T3ENScVymJQ.info.json").write_text(json.dumps(INFO_JSON), encoding="utf-8")
    factory, holder = _factory(info)

    result = YtDlpDownloader(tmp_path, ydl_factory=factory).download("https://youtu.be/T3ENScVymJQ")

    assert holder["ydl"].calls == [("https://youtu.be/T3ENScVymJQ", True)]
    assert result.video_path == video_path
    assert result.video_id == "T3ENScVymJQ"
    assert result.duration == 2820.0
    assert result.info_json_path == tmp_path / "T3ENScVymJQ.info.json"
    assert [c.title for c in result.chapters] == ["Abertura", "Pauta economica"]


def test_download_cai_para_prepare_filename_e_sem_info_json(tmp_path):
    fallback = tmp_path / "fallback.mp4"
    factory, _ = _factory(dict(INFO_JSON), filename=str(fallback))

    result = YtDlpDownloader(tmp_path, ydl_factory=factory).download("https://youtu.be/x")

    assert result.video_path == fallback
    assert result.info_json_path is None


def test_download_falha_quando_yt_dlp_nao_retorna_info(tmp_path):
    factory, _ = _factory(None)

    with pytest.raises(DownloadError):
        YtDlpDownloader(tmp_path, ydl_factory=factory).download("https://youtu.be/x")


class ExplodingYdl:
    """Simula o 403/"Sign in to confirm you're not a bot" do yt-dlp: qualquer chamada de
    rede falha. Usado pra provar que o cache-hit NUNCA fala com a rede (P2.2)."""

    def extract_info(self, url, download):
        raise DownloadError("Sign in to confirm you're not a bot")


def test_download_reaproveita_cache_local_sem_falar_com_a_rede(tmp_path):
    video_path = tmp_path / "T3ENScVymJQ.mp4"
    video_path.write_bytes(b"video ja baixado")
    (tmp_path / "T3ENScVymJQ.info.json").write_text(json.dumps(INFO_JSON), encoding="utf-8")

    def exploding_factory(opts):
        return ExplodingYdl()

    result = YtDlpDownloader(tmp_path, ydl_factory=exploding_factory).download(
        "https://youtu.be/T3ENScVymJQ"
    )

    assert result.video_path == video_path
    assert result.video_id == "T3ENScVymJQ"
    assert result.duration == 2820.0
    assert result.info_json_path == tmp_path / "T3ENScVymJQ.info.json"
    assert [c.title for c in result.chapters] == ["Abertura", "Pauta economica"]


def test_download_sem_video_em_cache_cai_pro_download_normal(tmp_path):
    (tmp_path / "T3ENScVymJQ.info.json").write_text(json.dumps(INFO_JSON), encoding="utf-8")
    info = dict(INFO_JSON, requested_downloads=[{"filepath": str(tmp_path / "T3ENScVymJQ.mp4")}])
    factory, holder = _factory(info)

    YtDlpDownloader(tmp_path, ydl_factory=factory).download("https://youtu.be/T3ENScVymJQ")

    assert holder["ydl"].calls == [("https://youtu.be/T3ENScVymJQ", True)]


def test_download_url_nao_reconhecida_cai_pro_download_normal(tmp_path):
    factory, holder = _factory(dict(INFO_JSON, requested_downloads=[{"filepath": "ignorado.mp4"}]))

    YtDlpDownloader(tmp_path, ydl_factory=factory).download("https://example.com/video")

    assert holder["ydl"].calls == [("https://example.com/video", True)]


class FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class FakeVideos:
    def __init__(self, response):
        self._response = response
        self.kwargs = None

    def list(self, **kwargs):
        self.kwargs = kwargs
        return FakeRequest(self._response)


class FakeYouTubeClient:
    def __init__(self, response):
        self._videos = FakeVideos(response)

    def videos(self):
        return self._videos


API_RESPONSE = {
    "items": [
        {
            "id": "T3ENScVymJQ",
            "snippet": {
                "title": "Live do Missao",
                "description": "Descricao oficial",
                "tags": ["missao", "renan santos"],
                "channelTitle": "Missao",
                "publishedAt": "2026-08-01T12:00:00Z",
                "thumbnails": {
                    "default": {"url": "http://img/default.jpg"},
                    "maxres": {"url": "http://img/maxres.jpg"},
                },
            },
            "contentDetails": {"duration": "PT47M12S"},
            "status": {"license": "youtube"},
        }
    ]
}


def test_pick_thumbnail_prefere_maior_resolucao():
    assert pick_thumbnail(API_RESPONSE["items"][0]["snippet"]["thumbnails"]) == "http://img/maxres.jpg"
    assert pick_thumbnail({"medium": {"url": "http://img/m.jpg"}}) == "http://img/m.jpg"
    assert pick_thumbnail(None) is None


def test_metadata_fetcher_parseia_resposta_da_data_api():
    client = FakeYouTubeClient(API_RESPONSE)
    fetcher = YouTubeMetadataFetcher(client_factory=lambda: client)

    metadata = fetcher.fetch("T3ENScVymJQ")

    assert client.videos().kwargs == {"part": "snippet,contentDetails,status", "id": "T3ENScVymJQ"}
    assert metadata.title == "Live do Missao"
    assert metadata.description == "Descricao oficial"
    assert metadata.tags == ("missao", "renan santos")
    assert metadata.duration == "PT47M12S"
    assert metadata.thumbnail_url == "http://img/maxres.jpg"
    assert metadata.license == "youtube"


def test_metadata_fetcher_nao_cria_client_ate_o_primeiro_fetch():
    calls = []

    def factory():
        calls.append(1)
        return FakeYouTubeClient(API_RESPONSE)

    fetcher = YouTubeMetadataFetcher(client_factory=factory)
    assert calls == []

    fetcher.fetch("T3ENScVymJQ")
    fetcher.fetch("T3ENScVymJQ")
    assert calls == [1]


def test_metadata_fetcher_usa_client_padrao_do_projeto(monkeypatch):
    client = FakeYouTubeClient(API_RESPONSE)
    monkeypatch.setattr("clipador.youtube.client.get_client", lambda: client)

    assert YouTubeMetadataFetcher().fetch("T3ENScVymJQ").video_id == "T3ENScVymJQ"


def test_metadata_fetcher_falha_sem_itens():
    fetcher = YouTubeMetadataFetcher(client_factory=lambda: FakeYouTubeClient({"items": []}))

    with pytest.raises(MetadataError):
        fetcher.fetch("inexistente")
