"""Testes do manifesto de selecao: trechos usados por formato + indice de clip_id."""

from clipador.select.manifest import SelectionManifest, load_manifest, save_manifest
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT


def test_allocate_index_devolve_indice_sequencial_por_formato():
    manifest = SelectionManifest()

    assert manifest.allocate_index(SHORT_FORMAT) == 0
    assert manifest.allocate_index(SHORT_FORMAT) == 1
    assert manifest.allocate_index(LONG_FORMAT) == 0  # indice proprio, nao compartilha com short


def test_allocate_index_nao_marca_o_trecho_como_usado():
    """allocate_index so reserva o numero da pasta - o trecho so vira "usado" (excluido
    de selecoes futuras) via mark_used, chamado depois do export dar certo (ver P2.1)."""
    manifest = SelectionManifest()

    manifest.allocate_index(SHORT_FORMAT)

    assert manifest.ranges_for(SHORT_FORMAT) == []


def test_mark_used_registra_o_trecho_sem_mexer_no_indice():
    manifest = SelectionManifest()
    index_antes = manifest.allocate_index(SHORT_FORMAT)

    manifest.mark_used(SHORT_FORMAT, 0, 10)

    assert manifest.ranges_for(SHORT_FORMAT) == [(0, 10)]
    assert manifest.allocate_index(SHORT_FORMAT) == index_antes + 1


def test_ranges_for_isola_por_formato():
    manifest = SelectionManifest()
    manifest.mark_used(SHORT_FORMAT, 0, 10)
    manifest.mark_used(LONG_FORMAT, 100, 900)

    assert manifest.ranges_for(SHORT_FORMAT) == [(0, 10)]
    assert manifest.ranges_for(LONG_FORMAT) == [(100, 900)]


def test_ranges_for_formato_sem_uso_devolve_vazio():
    assert SelectionManifest().ranges_for(SHORT_FORMAT) == []


def test_save_e_load_preserva_ranges_e_indices(tmp_path):
    manifest = SelectionManifest()
    manifest.allocate_index(SHORT_FORMAT)
    manifest.mark_used(SHORT_FORMAT, 0, 10)
    manifest.allocate_index(SHORT_FORMAT)
    manifest.mark_used(SHORT_FORMAT, 50, 70)
    manifest.allocate_index(LONG_FORMAT)
    manifest.mark_used(LONG_FORMAT, 200, 900)
    path = tmp_path / "manifest.json"

    save_manifest(manifest, path)
    loaded = load_manifest(path)

    assert loaded.ranges_for(SHORT_FORMAT) == [(0, 10), (50, 70)]
    assert loaded.ranges_for(LONG_FORMAT) == [(200, 900)]
    # proximo indice continua de onde parou (nao reseta ao recarregar do disco)
    assert loaded.allocate_index(SHORT_FORMAT) == 2
    assert loaded.allocate_index(LONG_FORMAT) == 1


def test_load_manifest_sem_arquivo_devolve_manifesto_vazio(tmp_path):
    manifest = load_manifest(tmp_path / "inexistente.json")

    assert manifest.used_ranges == {}
    assert manifest.allocate_index(SHORT_FORMAT) == 0
