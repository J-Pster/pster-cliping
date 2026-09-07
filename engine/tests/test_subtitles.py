"""Testes 100% offline do modulo de legendas (.ass): geracao pura + burn_in mockado.

As fontes embarcadas em `assets/fonts` sao lidas de verdade (medicao de largura), mas
nenhum teste aqui chama ffmpeg.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pysubs2
import pytest

from clipador.select.models import LONG_FORMAT, SHORT_FORMAT
from clipador.subtitles import (
    AssSubtitleBuilder,
    SubtitleStyle,
    build_ass,
    build_subtitle_style,
    burn_in,
    save_ass,
)
from clipador.subtitles.builder import fit_scale
from clipador.subtitles.cues import render_text
from clipador.subtitles.fonts import BUNDLED_FONTS, FontNotFoundError, TextMeasurer, em_scale, font_file_for
from clipador.subtitles.presets import PRESET_NAMES
from clipador.transcribe.models import Word

FONTS_DIR = Path("assets/fonts")


def _make_words(count: int, *, word_duration: float = 0.4, gap: float = 0.05) -> list[Word]:
    words = []
    cursor = 0.0
    for i in range(count):
        start = cursor
        end = start + word_duration
        words.append(Word(id=i, text=f"palavra{i}", start=start, end=end))
        cursor = end + gap
    return words


def _words_from(text: str, *, word_duration: float = 0.4, gap: float = 0.05) -> list[Word]:
    words = []
    cursor = 0.0
    for i, token in enumerate(text.split()):
        words.append(Word(id=i, text=token, start=cursor, end=cursor + word_duration))
        cursor += word_duration + gap
    return words


def _style(**overrides) -> SubtitleStyle:
    """Estilo pequeno e deterministico: fonte cabe muita palavra por linha, entao os
    testes de segmentacao exercitam a regra que querem testar, nao a largura."""
    base = {"font_size": 40, "fonts_dir": FONTS_DIR, "fade_in_ms": 0, "fade_out_ms": 0}
    return SubtitleStyle(**{**base, **overrides})


def _dialogues(content: str) -> list[str]:
    return [line for line in content.splitlines() if line.startswith("Dialogue:")]


# --------------------------------------------------------------------------- fontes


def test_todas_as_fontes_embarcadas_existem_no_repo():
    for family in BUNDLED_FONTS:
        assert font_file_for(family, FONTS_DIR).is_file()


def test_fonte_desconhecida_falha_alto_em_vez_de_cair_num_fallback():
    with pytest.raises(FontNotFoundError, match="nao esta embarcada"):
        font_file_for("Comic Sans MS", FONTS_DIR)


def test_em_scale_reproduz_a_conversao_de_fontsize_do_libass():
    """`Fontsize` do ASS nao e o em: o libass converte por
    unitsPerEm / (usWinAscent + usWinDescent). Valores conferidos contra o render real
    do libass (erro < 0.5%); se algum divergir, a quebra de linha e o `\\pos` do modo
    pop saem errados."""
    esperado = {
        "Montserrat ExtraBold": 0.6402,
        "Anton": 0.5769,
        "Archivo Black": 0.7424,
        "Bebas Neue": 0.7692,
    }
    for family, fator in esperado.items():
        assert em_scale(str(font_file_for(family, FONTS_DIR))) == pytest.approx(fator, abs=0.001)


def test_medicao_e_linear_no_font_size():
    pequeno = TextMeasurer.for_style("Montserrat ExtraBold", 50, FONTS_DIR)
    grande = TextMeasurer.for_style("Montserrat ExtraBold", 200, FONTS_DIR)

    assert grande.width("TESTE") == pytest.approx(pequeno.width("TESTE") * 4, rel=1e-6)


def test_largura_de_uma_frase_e_a_soma_das_palavras_com_os_espacos():
    m = TextMeasurer.for_style("Montserrat ExtraBold", 100, FONTS_DIR)

    assert m.width("TRINTA DIAS") == pytest.approx(
        m.width("TRINTA") + m.space_width + m.width("DIAS"), rel=1e-6
    )


# --------------------------------------------------------------------------- estrutura


def test_build_ass_produces_valid_header_sections():
    content = build_ass(_make_words(3), _style())

    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert content.index("[Script Info]") < content.index("[V4+ Styles]") < content.index("[Events]")
    assert "Format: Name, Fontname" in content
    assert "Style: Default," in content
    assert "Format: Layer, Start, End, Style" in content


def test_wrapstyle_2_desliga_a_quebra_automatica_do_libass():
    """A quebra de linha e decidida aqui, com a largura medida na fonte real. Deixar o
    libass quebrar de novo mudaria o numero de linhas e faria o bloco de legenda pular
    de altura a cada cue."""
    assert "WrapStyle: 2" in build_ass(_make_words(6), _style())


def test_build_com_style_sobrescreve_sem_alterar_o_style_do_builder():
    words = _make_words(3)
    builder = AssSubtitleBuilder(_style())  # default: 1080x1920 (formato curto)
    long_style = _style(play_res_x=1920, play_res_y=1080, margin_v=100)

    content = builder.build(words, style=long_style)

    assert "PlayResX: 1920" in content
    assert "PlayResY: 1080" in content
    assert builder.style.play_res_x == 1080  # instancia do builder nao muda

    content_default = builder.build(words)
    assert "PlayResX: 1080" in content_default
    assert "PlayResY: 1920" in content_default


# --------------------------------------------------------------------------- segmentacao


def test_cue_fecha_no_teto_de_palavras():
    cues = AssSubtitleBuilder(_style(max_words_per_cue=3)).cues(_make_words(9))

    assert [len(cue.words) for cue in cues] == [3, 3, 3]


def test_cue_fecha_em_fim_de_frase():
    words = _words_from("um dois tres. quatro cinco seis")

    cues = AssSubtitleBuilder(_style(max_words_per_cue=6)).cues(words)

    assert [[w.text for w in cue.words] for cue in cues] == [
        ["UM", "DOIS", "TRES"],
        ["QUATRO", "CINCO", "SEIS"],
    ]


def test_cue_nao_fecha_em_fim_de_frase_curto_demais():
    """Um "Sim." isolado viraria uma cue de 400ms piscando na tela; ela e absorvida na
    proxima em vez de virar evento proprio."""
    words = _words_from("sim. entao vamos adiante", word_duration=0.4, gap=0.0)

    cues = AssSubtitleBuilder(_style(min_cue_seconds=1.0)).cues(words)

    assert len(cues) == 1
    assert [w.text for w in cues[0].words] == ["SIM", "ENTAO", "VAMOS", "ADIANTE"]


def test_silencio_longo_quebra_a_cue():
    words = [
        Word(id=0, text="antes", start=0.0, end=0.4),
        Word(id=1, text="depois", start=3.0, end=3.4),
    ]

    cues = AssSubtitleBuilder(_style(max_gap_seconds=0.6)).cues(words)

    assert [[w.text for w in cue.words] for cue in cues] == [["ANTES"], ["DEPOIS"]]


def test_cue_respeita_o_teto_de_duracao():
    words = _make_words(8, word_duration=0.9, gap=0.05)

    cues = AssSubtitleBuilder(_style(max_cue_seconds=2.0, max_words_per_cue=8)).cues(words)

    assert cues, "esperava pelo menos uma cue"
    for cue in cues:
        assert cue.words[-1].end - cue.words[0].start <= 2.0 + 1e-9


def test_cue_nunca_passa_de_max_lines_nem_da_largura_util():
    style = _style(font_size=120, max_lines=2, max_words_per_cue=8)
    builder = AssSubtitleBuilder(style)
    measurer = TextMeasurer.for_style(style.font_name, style.font_size, style.fonts_dir)
    words = _words_from(
        "criacao de uma comissao nacional de classificacao composta por agencias federais"
    )

    for cue in builder.cues(words):
        assert len(cue.lines) <= 2
        # A unica excecao permitida e a palavra que sozinha nao cabe: essa e condensada
        # no render (fit_scale), nao quebrada.
        for line in cue.lines:
            largura = sum(w.width for w in line) + measurer.space_width * (len(line) - 1)
            assert largura <= style.usable_width or len(line) == 1


def test_quebra_de_linha_e_equilibrada_e_nao_gulosa():
    """Minimax: duas linhas parecidas em vez de uma cheia e outra com uma palavra."""
    style = _style(font_size=160, max_lines=2, max_words_per_cue=4)
    cues = AssSubtitleBuilder(style).cues(_words_from("alfa beta gama delta"))

    assert len(cues) == 1
    assert [len(line) for line in cues[0].lines] == [2, 2]


def test_cue_segura_a_legenda_no_silencio_seguinte_sem_invadir_a_proxima():
    words = [
        Word(id=0, text="antes", start=0.0, end=1.0),
        Word(id=1, text="depois", start=5.0, end=6.0),
    ]

    cues = AssSubtitleBuilder(_style(hold_seconds=0.35, max_gap_seconds=0.6)).cues(words)

    assert cues[0].end == pytest.approx(1.35)  # segurou 350ms alem da fala
    assert cues[1].start == pytest.approx(5.0)


def test_hold_nao_sobrepoe_a_cue_seguinte():
    words = [
        Word(id=0, text="antes", start=0.0, end=1.0),
        Word(id=1, text="depois", start=1.2, end=2.0),
    ]

    cues = AssSubtitleBuilder(_style(hold_seconds=0.35, max_words_per_cue=1)).cues(words)

    assert cues[0].end <= cues[1].start


# --------------------------------------------------------------------------- texto


def test_render_text_sobe_a_caixa_e_tira_a_pontuacao_das_pontas():
    assert render_text("improrrogáveis,", uppercase=True, strip_punctuation=True) == "IMPRORROGÁVEIS"
    assert render_text("(assim)", uppercase=True, strip_punctuation=True) == "ASSIM"


def test_render_text_preserva_hifen_e_apostrofo():
    """Sao parte de palavra em PT-BR, nao pontuacao de frase."""
    assert render_text("bem-vindo", uppercase=False, strip_punctuation=True) == "bem-vindo"
    assert render_text("d'agua", uppercase=False, strip_punctuation=True) == "d'agua"


def test_style_sem_uppercase_preserva_a_caixa_original():
    content = build_ass(_words_from("Brasil precisa"), _style(uppercase=False))

    assert "Brasil" in content
    assert "BRASIL" not in content


# --------------------------------------------------------------------------- modo pop


def test_pop_emite_um_evento_por_palavra_com_pos_explicito():
    words = _make_words(4)
    style = _style(highlight_mode="pop", max_words_per_cue=4)

    content = AssSubtitleBuilder(style).build(words)
    dialogues = _dialogues(content)

    assert len(dialogues) == len(words)
    assert all("\\pos(" in line and "\\an5" in line for line in dialogues)


def test_pop_anima_escala_e_cor_no_instante_da_palavra():
    style = _style(highlight_mode="pop", pop_scale=112, pop_ms=110, max_words_per_cue=2)
    words = [
        Word(id=0, text="um", start=0.0, end=0.4),
        Word(id=1, text="dois", start=0.5, end=0.9),
    ]

    parsed = pysubs2.SSAFile.from_string(AssSubtitleBuilder(style).build(words))

    # A segunda palavra comeca 500ms depois do inicio da cue: e nesse offset que o
    # `\t` dela dispara.
    segundo = parsed.events[1].text
    assert "\\t(500,610,\\fscx112\\fscy112" in segundo
    assert "\\t(610,720,\\fscx100\\fscy100)" in segundo


def test_pop_volta_a_cor_base_quando_o_destaque_nao_persiste():
    style = _style(highlight_mode="pop", highlight_persists=False, max_words_per_cue=2)

    primeiro = pysubs2.SSAFile.from_string(
        AssSubtitleBuilder(style).build(_make_words(2))
    ).events[0].text

    # duas transicoes de cor: entra no destaque e volta pro branco
    assert primeiro.count("\\1c&HFFFFFF&") == 2


def test_pop_mantem_o_destaque_acumulado_quando_persiste():
    style = _style(highlight_mode="pop", highlight_persists=True, max_words_per_cue=2)

    primeiro = pysubs2.SSAFile.from_string(
        AssSubtitleBuilder(style).build(_make_words(2))
    ).events[0].text

    assert primeiro.count("\\1c&HFFFFFF&") == 1  # so a cor base inicial


def test_pop_centraliza_a_linha_no_eixo_do_quadro():
    style = _style(highlight_mode="pop", max_words_per_cue=1, play_res_x=1080)

    conteudo = AssSubtitleBuilder(style).build(_make_words(1))
    (x,) = re.findall(r"\\pos\((\d+),\d+\)", conteudo)

    assert int(x) == 540  # palavra unica centrada


def test_pop_posiciona_as_linhas_acima_da_margem_inferior():
    style = _style(highlight_mode="pop", max_words_per_cue=1, play_res_y=1920, margin_v=840)

    conteudo = AssSubtitleBuilder(style).build(_make_words(1))
    (y,) = re.findall(r"\\pos\(\d+,(\d+)\)", conteudo)

    # alignment 2: o bloco fica `margin_v` acima da base do quadro.
    assert 1920 - 840 - style.line_spacing * 40 <= int(y) <= 1920 - 840


# --------------------------------------------------------------------------- modos karaoke


@pytest.mark.parametrize(("mode", "tag"), [("sweep", "kf"), ("switch", "k")])
def test_karaoke_emite_um_evento_por_cue_com_a_tag_do_modo(mode, tag):
    words = _make_words(4)
    style = _style(highlight_mode=mode, max_words_per_cue=4)

    content = AssSubtitleBuilder(style).build(words)

    assert len(_dialogues(content)) == 1
    parsed = pysubs2.SSAFile.from_string(content)
    assert len(re.findall(rf"\\{tag}\d+", parsed.events[0].text)) >= len(words)


def test_karaoke_alcanca_cada_palavra_no_offset_certo():
    style = _style(highlight_mode="sweep", max_words_per_cue=4)
    words = _make_words(4)
    builder = AssSubtitleBuilder(style)
    cue = builder.cues(words)[0]

    parsed = pysubs2.SSAFile.from_string(builder.build(words))
    blocks = re.findall(r"\{\\kf(\d+)\}([^{]*)", parsed.events[0].text)

    cumulative_cs = 0
    remaining = iter(cue.words)
    for duration_cs, text in blocks:
        stripped = text.replace("\\N", " ").strip()
        if stripped:
            word = next(remaining)
            assert abs((cue.start + cumulative_cs / 100) - word.start) < 0.02
            assert stripped == word.text
        cumulative_cs += int(duration_cs)
    assert next(remaining, None) is None


def test_karaoke_mapeia_destaque_em_primary_e_base_em_secondary():
    """Convencao do formato ASS: `PrimaryColour` e a porcao ja cantada (a palavra
    destacada) e `SecondaryColour` a que a varredura ainda nao alcancou."""
    style = _style(
        highlight_mode="switch", highlight_color="&H0000FFFF", primary_color="&H00FFFFFF"
    )

    parsed = pysubs2.SSAFile.from_string(build_ass(_make_words(2), style))
    ass_style = parsed.styles["Default"]

    assert (ass_style.primarycolor.r, ass_style.primarycolor.g, ass_style.primarycolor.b) == (255, 255, 0)
    assert (ass_style.secondarycolor.r, ass_style.secondarycolor.g, ass_style.secondarycolor.b) == (255, 255, 255)


def test_pop_usa_a_cor_base_como_primary_porque_nao_ha_karaoke():
    style = _style(highlight_mode="pop", highlight_color="&H0000FFFF", primary_color="&H00FFFFFF")

    parsed = pysubs2.SSAFile.from_string(build_ass(_make_words(2), style))
    ass_style = parsed.styles["Default"]

    assert (ass_style.primarycolor.r, ass_style.primarycolor.g, ass_style.primarycolor.b) == (255, 255, 255)


def test_quebra_de_linha_vira_N_no_texto_do_evento_karaoke():
    style = _style(highlight_mode="switch", font_size=150, max_lines=2, max_words_per_cue=4)

    content = AssSubtitleBuilder(style).build(_words_from("alfa beta gama delta"))

    assert "\\N" in pysubs2.SSAFile.from_string(content).events[0].text


# --------------------------------------------------------------------------- enfase e fit


def test_enfase_pinta_a_palavra_com_a_cor_propria_no_modo_pop():
    style = _style(highlight_mode="pop", emphasis_color="&H0000E5FF", max_words_per_cue=3)

    parsed = pysubs2.SSAFile.from_string(
        AssSubtitleBuilder(style).build(_make_words(3), emphasis_word_ids=frozenset({1}))
    )

    # override de cor no ASS e `&HBBGGRR&`, sem o alfa que o campo de estilo carrega
    assert "&H00E5FF&" in parsed.events[1].text
    assert "&H00E5FF&" not in parsed.events[0].text


def test_enfase_no_karaoke_muda_o_contorno_e_nao_o_preenchimento():
    """No modo karaoke o preenchimento pertence ao mecanismo `\\k` (primary/secondary);
    um override `\\1c` no meio dele mataria a troca de cor da palavra."""
    style = _style(highlight_mode="switch", emphasis_color="&H0000E5FF", max_words_per_cue=3)

    texto = pysubs2.SSAFile.from_string(
        AssSubtitleBuilder(style).build(_make_words(3), emphasis_word_ids=frozenset({1}))
    ).events[0].text

    assert "\\3c&H00E5FF&" in texto
    assert "\\1c" not in texto


def test_fit_scale_condensa_a_cue_que_estoura_a_largura():
    style = _style(font_size=400, max_lines=1, max_words_per_cue=1)
    builder = AssSubtitleBuilder(style)
    measurer = TextMeasurer.for_style(style.font_name, style.font_size, style.fonts_dir)
    cue = builder.cues(_words_from("improrrogaveis"))[0]

    escala = fit_scale(cue, style, measurer.space_width)

    assert escala < 100
    assert "\\fscx" in builder.build(_words_from("improrrogaveis"))


def test_fit_scale_nao_mexe_na_cue_que_cabe():
    style = _style(font_size=40)
    builder = AssSubtitleBuilder(style)
    measurer = TextMeasurer.for_style(style.font_name, style.font_size, style.fonts_dir)

    assert fit_scale(builder.cues(_words_from("ok"))[0], style, measurer.space_width) == 100


# --------------------------------------------------------------------------- presets


def test_todo_preset_resolve_estilo_para_os_dois_formatos():
    for name in PRESET_NAMES:
        for clip_format in (SHORT_FORMAT, LONG_FORMAT):
            style = build_subtitle_style(name, clip_format)
            assert style.font_size > 0
            assert style.usable_width > 0
            assert style.font_name in BUNDLED_FONTS


def test_legenda_do_vertical_pesa_mais_que_a_do_horizontal_em_fracao_de_altura():
    """Regressao do bug de inversao: com `font_size` fixo em pixel nos dois formatos, o
    mesmo 72 valia 3.75% da altura em 1920 e 6.7% em 1080 - a legenda do vertical, que e
    a que mais precisa ser grande, era proporcionalmente quase METADE da do horizontal."""
    for name in PRESET_NAMES:
        curto = build_subtitle_style(name, SHORT_FORMAT)
        longo = build_subtitle_style(name, LONG_FORMAT)

        fracao_curto = curto.font_size / curto.play_res_y
        fracao_longo = longo.font_size / longo.play_res_y
        assert fracao_curto >= fracao_longo * 0.9


def test_preset_desconhecido_falha_alto():
    with pytest.raises(ValueError, match="Preset de legenda desconhecido"):
        build_subtitle_style("inexistente", SHORT_FORMAT)


def test_formato_desconhecido_falha_alto():
    with pytest.raises(ValueError, match="Formato de clipe desconhecido"):
        build_subtitle_style("impacto", "quadrado_1x1")


def test_style_rejeita_highlight_mode_invalido():
    with pytest.raises(ValueError, match="highlight_mode invalido"):
        SubtitleStyle(highlight_mode="karaoke")


def test_style_rejeita_margens_maiores_que_o_quadro():
    with pytest.raises(ValueError, match="largura util"):
        SubtitleStyle(margin_l=600, margin_r=600, play_res_x=1080)


# --------------------------------------------------------------------------- IO / burn


def test_save_ass_writes_file(tmp_path):
    target = tmp_path / "nested" / "legenda.ass"

    save_ass("conteudo de teste", target)

    assert target.read_text(encoding="utf-8") == "conteudo de teste"


def test_burn_in_invokes_runner_with_expected_command(tmp_path):
    video_path = tmp_path / "clipe.mp4"
    ass_path = tmp_path / "legenda.ass"
    output_path = tmp_path / "saida" / "clipe_legendado.mp4"

    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs))

        class _Result:
            returncode = 0

        return _Result()

    burn_in(video_path, ass_path, output_path, runner=fake_runner)

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd[0] == "ffmpeg"
    assert str(video_path) in cmd
    assert str(output_path) in cmd
    assert kwargs.get("check") is True

    filter_arg = cmd[cmd.index("-vf") + 1]
    assert filter_arg.startswith("ass=")
    assert "legenda.ass" in filter_arg

    assert output_path.parent.exists()


def test_burn_in_envolve_o_path_em_aspas_simples_para_o_filtro_ass(tmp_path):
    """Sem aspas simples o parser de filtergraph do ffmpeg quebra em Windows com drive
    letter (ex: `C:`) mesmo com o `:` escapado - confirmado rodando o comando de
    verdade (erro `original_size ... Invalid argument`). Regressao: nao remover as aspas."""
    calls = []
    burn_in(
        tmp_path / "clipe.mp4",
        tmp_path / "legenda.ass",
        tmp_path / "saida.mp4",
        runner=lambda cmd, **kwargs: calls.append(cmd),
    )

    filter_arg = calls[0][calls[0].index("-vf") + 1]
    inner = filter_arg[len("ass=") :]
    assert inner.startswith("'") and inner.endswith("'")


def test_burn_in_passa_fontsdir_com_o_mesmo_escape_do_path_do_ass(tmp_path):
    """Sem `fontsdir` o libass procura a fonte no fontconfig do sistema e, se nao achar,
    cai numa fonte generica EM SILENCIO - o clipe sai errado sem nada no log."""
    fonts_dir = tmp_path / "fontes"
    fonts_dir.mkdir()
    calls = []

    burn_in(
        tmp_path / "clipe.mp4",
        tmp_path / "legenda.ass",
        tmp_path / "saida.mp4",
        fonts_dir=fonts_dir,
        runner=lambda cmd, **kwargs: calls.append(cmd),
    )

    filter_arg = calls[0][calls[0].index("-vf") + 1]
    assert ":fontsdir='" in filter_arg
    assert "fontes" in filter_arg


def test_burn_in_falha_alto_quando_o_diretorio_de_fontes_nao_existe(tmp_path):
    with pytest.raises(FileNotFoundError, match="fontes da legenda"):
        burn_in(
            tmp_path / "clipe.mp4",
            tmp_path / "legenda.ass",
            tmp_path / "saida.mp4",
            fonts_dir=tmp_path / "inexistente",
            runner=lambda cmd, **kwargs: None,
        )


def test_burn_in_sem_fonts_dir_nao_passa_a_opcao(tmp_path):
    calls = []
    burn_in(
        tmp_path / "clipe.mp4",
        tmp_path / "legenda.ass",
        tmp_path / "saida.mp4",
        runner=lambda cmd, **kwargs: calls.append(cmd),
    )

    assert "fontsdir" not in calls[0][calls[0].index("-vf") + 1]


def test_burn_in_never_calls_real_subprocess_run(monkeypatch, tmp_path):
    import subprocess

    def fail_if_called(*args, **kwargs):
        raise AssertionError("burn_in nao deve invocar subprocess.run real quando um runner é injetado")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    calls = []
    burn_in(
        tmp_path / "v.mp4",
        tmp_path / "s.ass",
        tmp_path / "out.mp4",
        runner=lambda cmd, **kwargs: calls.append(cmd),
    )

    assert len(calls) == 1


def test_estilo_do_preset_pode_apontar_para_outro_diretorio_de_fontes(tmp_path):
    style = replace(build_subtitle_style("impacto", SHORT_FORMAT), fonts_dir=tmp_path)

    assert style.fonts_dir == tmp_path
