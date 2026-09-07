from clipador.metadata.censor import censor_text, is_sensitive_word


def test_censor_text_troca_vogal_por_numero_em_palavra_sensivel():
    assert censor_text("Plano para matar Moraes") == "Plano para m4t4r Moraes"


def test_censor_text_cobre_conjugacoes_do_mesmo_radical():
    assert censor_text("Ele mataria e mataram o alvo") == "Ele m4t4r14 e m4t4r4m o alvo"


def test_censor_text_cobre_bomba_assassinato_roubo():
    assert censor_text("bomba no aeroporto") == "b0mb4 no aeroporto"
    assert censor_text("plano de assassinato") == "plano de 4ss4ss1n4t0"
    assert censor_text("Roubo de Celular") == "R0ub0 de Celular"


def test_censor_text_preserva_vocabulario_politico_normal():
    text = "Golpe de Estado, prisao preventiva e condenacao no STF"
    assert censor_text(text) == text


def test_censor_text_string_vazia():
    assert censor_text("") == ""


def test_censor_text_preserva_pontuacao_e_espacamento():
    assert censor_text("matar? sim, matar!") == "m4t4r? sim, m4t4r!"


def test_is_sensitive_word_ignora_acento_e_caixa():
    assert is_sensitive_word("SUICÍDIO")
    assert is_sensitive_word("Sequestrado")
    assert not is_sensitive_word("golpe")
    assert not is_sensitive_word("prisao")


def test_censor_text_cobre_preterito_matou_sem_ambiguidade_de_mata():
    assert censor_text('"Prendeu, Matou?" foi o lema') == '"Prendeu, M4t0u?" foi o lema'
    assert censor_text("ele matou, matei, mataram") == "ele m4t0u, m4t31, m4t4r4m"


def test_censor_text_nao_confunde_mato_grosso_com_o_verbo_matar():
    assert censor_text("recapeada em Mato Grosso") == "recapeada em Mato Grosso"


def test_censor_text_nao_confunde_materia_e_matematica_com_matar():
    assert censor_text("essa materia de matematica") == "essa materia de matematica"


def test_censor_text_nao_confunde_bombeiro_com_bomba():
    assert censor_text("o bombeiro apagou o incendio") == "o bombeiro apagou o incendio"
    assert censor_text("bomba no aeroporto") == "b0mb4 no aeroporto"
