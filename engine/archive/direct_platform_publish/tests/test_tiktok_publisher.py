import base64
import hashlib

from clipador.publish.tiktok_publisher import MAX_CHUNK_BYTES, MIN_CHUNK_BYTES, _chunk_plan, _pkce_pair


def test_chunk_plan_video_pequeno_vai_num_chunk_so():
    chunk_size, total = _chunk_plan(MIN_CHUNK_BYTES - 1)

    assert chunk_size == MIN_CHUNK_BYTES - 1
    assert total == 1


def test_chunk_plan_video_grande_usa_chunks_de_64mb():
    video_size = MAX_CHUNK_BYTES * 2 + 1

    chunk_size, total = _chunk_plan(video_size)

    assert chunk_size == MAX_CHUNK_BYTES
    assert total == 3
    assert (total - 1) * chunk_size < video_size <= total * chunk_size


def test_pkce_pair_challenge_bate_com_sha256_do_verifier():
    verifier, challenge = _pkce_pair()

    esperado = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
    esperado = esperado.rstrip(b"=").decode("ascii")

    assert challenge == esperado
    assert "=" not in verifier
    assert "=" not in challenge
