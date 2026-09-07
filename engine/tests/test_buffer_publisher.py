from pathlib import Path

import pytest

from clipador.publish import buffer_publisher
from clipador.publish.models import GROUP_COMMIT_CIVICO, PLATFORM_YOUTUBE, PublishError

SENTINEL_STAGED = object()


def test_channel_id_sem_env_var_levanta_publish_error(monkeypatch):
    monkeypatch.delenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", raising=False)

    with pytest.raises(PublishError, match="BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE"):
        buffer_publisher._channel_id(GROUP_COMMIT_CIVICO, PLATFORM_YOUTUBE)


def test_channel_id_resolve_com_env_var_setada(monkeypatch):
    monkeypatch.setenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", "chan_123")

    assert buffer_publisher._channel_id(GROUP_COMMIT_CIVICO, PLATFORM_YOUTUBE) == "chan_123"


def test_channel_id_grupo_desconhecido_levanta_publish_error():
    with pytest.raises(PublishError, match="Grupo"):
        buffer_publisher._channel_id("grupo_inexistente", PLATFORM_YOUTUBE)


def test_channel_id_plataforma_desconhecida_levanta_publish_error():
    with pytest.raises(PublishError, match="Plataforma"):
        buffer_publisher._channel_id(GROUP_COMMIT_CIVICO, "orkut")


def test_list_channels_parseia_resposta(mocker):
    mocker.patch.object(buffer_publisher, "get_organization_id", return_value="org_1")
    request_mock = mocker.patch.object(
        buffer_publisher,
        "graphql_request",
        return_value={"channels": [{"id": "chan_1", "name": "Meu Canal", "service": "youtube"}]},
    )

    channels = buffer_publisher.list_channels()

    assert channels == [{"id": "chan_1", "name": "Meu Canal", "service": "youtube"}]
    request_mock.assert_called_once_with(
        buffer_publisher._CHANNELS_QUERY, {"organizationId": "org_1"}
    )


def test_publish_caminho_feliz(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", "chan_123")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    mocker.patch.object(
        buffer_publisher, "stage_video", return_value=(SENTINEL_STAGED, "https://x/video.mp4")
    )
    delete_staged_mock = mocker.patch.object(buffer_publisher, "delete_staged")
    mocker.patch.object(
        buffer_publisher,
        "graphql_request",
        side_effect=[
            {"createPost": {"post": {"id": "post_1", "status": "scheduled"}}},
            {"editPost": {"post": {"id": "post_1", "status": "sending"}}},
            {"post": {"id": "post_1", "status": "sent"}},
        ],
    )

    result = buffer_publisher.publish(
        video_path, "Titulo", "Descricao", ["politica"], PLATFORM_YOUTUBE, GROUP_COMMIT_CIVICO
    )

    assert result.success is True
    assert result.remote_id == "post_1"
    delete_staged_mock.assert_called_once_with(SENTINEL_STAGED)


def test_publish_erro_na_criacao_do_post(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", "chan_123")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    mocker.patch.object(
        buffer_publisher, "stage_video", return_value=(SENTINEL_STAGED, "https://x/video.mp4")
    )
    delete_staged_mock = mocker.patch.object(buffer_publisher, "delete_staged")
    mocker.patch.object(
        buffer_publisher,
        "graphql_request",
        return_value={"createPost": {"message": "canal desconectado"}},
    )

    with pytest.raises(PublishError, match="canal desconectado"):
        buffer_publisher.publish(
            video_path, "Titulo", "Descricao", [], PLATFORM_YOUTUBE, GROUP_COMMIT_CIVICO
        )

    delete_staged_mock.assert_called_once_with(SENTINEL_STAGED)


def test_publish_erro_ao_disparar_share_now(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", "chan_123")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    mocker.patch.object(
        buffer_publisher, "stage_video", return_value=(SENTINEL_STAGED, "https://x/video.mp4")
    )
    delete_staged_mock = mocker.patch.object(buffer_publisher, "delete_staged")
    mocker.patch.object(
        buffer_publisher,
        "graphql_request",
        side_effect=[
            {"createPost": {"post": {"id": "post_1", "status": "scheduled"}}},
            {"editPost": {"message": "post ja foi publicado"}},
        ],
    )

    with pytest.raises(PublishError, match="post ja foi publicado"):
        buffer_publisher.publish(
            video_path, "Titulo", "Descricao", [], PLATFORM_YOUTUBE, GROUP_COMMIT_CIVICO
        )

    delete_staged_mock.assert_called_once_with(SENTINEL_STAGED)


def test_publish_status_error_no_polling(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", "chan_123")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    mocker.patch.object(
        buffer_publisher, "stage_video", return_value=(SENTINEL_STAGED, "https://x/video.mp4")
    )
    delete_staged_mock = mocker.patch.object(buffer_publisher, "delete_staged")
    mocker.patch.object(
        buffer_publisher,
        "graphql_request",
        side_effect=[
            {"createPost": {"post": {"id": "post_1", "status": "scheduled"}}},
            {"editPost": {"post": {"id": "post_1", "status": "sending"}}},
            {"post": {"id": "post_1", "status": "error", "error": {"message": "video invalido"}}},
        ],
    )

    with pytest.raises(PublishError, match="video invalido"):
        buffer_publisher.publish(
            video_path, "Titulo", "Descricao", [], PLATFORM_YOUTUBE, GROUP_COMMIT_CIVICO
        )

    delete_staged_mock.assert_called_once_with(SENTINEL_STAGED)


def test_publish_timeout_no_polling(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE", "chan_123")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    mocker.patch.object(
        buffer_publisher, "stage_video", return_value=(SENTINEL_STAGED, "https://x/video.mp4")
    )
    delete_staged_mock = mocker.patch.object(buffer_publisher, "delete_staged")
    mocker.patch.object(
        buffer_publisher,
        "graphql_request",
        side_effect=[
            {"createPost": {"post": {"id": "post_1", "status": "scheduled"}}},
            {"editPost": {"post": {"id": "post_1", "status": "sending"}}},
            {"post": {"id": "post_1", "status": "sending"}},
        ],
    )
    mocker.patch.object(buffer_publisher.time, "sleep")

    times = iter([0, buffer_publisher.CONTAINER_POLL_TIMEOUT_SECONDS + 1])
    mocker.patch.object(buffer_publisher.time, "monotonic", side_effect=lambda: next(times))

    with pytest.raises(PublishError, match="[Tt]imeout"):
        buffer_publisher.publish(
            video_path, "Titulo", "Descricao", [], PLATFORM_YOUTUBE, GROUP_COMMIT_CIVICO
        )

    delete_staged_mock.assert_called_once_with(SENTINEL_STAGED)
