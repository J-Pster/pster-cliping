# Clipador

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](engine/pyproject.toml)
[![Electron](https://img.shields.io/badge/app-Electron-47848F?logo=electron&logoColor=white)](app/package.json)

**Read this in [English](README.md).**

**Clipador** transforma um vídeo cru do YouTube (ou um arquivo local) em uma fila de
clipes curtos (9:16, formato Reels/Shorts/TikTok) e longos (16:9), já cortados,
legendados, com thumbnail e metadados prontos, para um humano só revisar e postar.

Nada é publicado automaticamente: o pipeline é 100% de **geração assistida**, o clipe
sempre passa por uma checagem editorial antes de ir ao ar.

## Índice

- [O que o projeto faz](#o-que-o-projeto-faz)
- [Como funciona (arquitetura)](#como-funciona-arquitetura)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Pré-requisitos](#pré-requisitos)
- [Instalação e primeira execução](#instalação-e-primeira-execução)
  - [1. Aplicativo desktop (recomendado)](#1-aplicativo-desktop-recomendado)
  - [2. Rodar o engine diretamente (CLI)](#2-rodar-o-engine-diretamente-cli)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Comandos úteis por parte do projeto](#comandos-úteis-por-parte-do-projeto)
- [Documentação adicional](#documentação-adicional)
- [Licença](#licença)

## O que o projeto faz

Você dá um link do YouTube (ou um arquivo de vídeo local) e uma categoria de conteúdo, e
o Clipador entrega, para cada clipe:

- **Seleção automática dos melhores trechos** do vídeo original, escolhidos por um LLM a
  partir da transcrição completa (não é corte por silêncio/cena genérico: o modelo lê o
  conteúdo e escolhe o que tem potencial de viralizar, com rerank e checagem de prosódia).
- **Reenquadramento vertical (9:16)** com detecção de rosto e de quem está falando, para
  o clipe já sair enquadrado como um Reels/Short de verdade, não um vídeo horizontal com
  barras pretas.
- **Legenda embutida estilo karaokê**, palavra a palavra, com presets visuais prontos
  (`impacto`, `anton`, `neon`, `classico`) e opção de destacar palavras-chave com cor
  própria.
- **Thumbnail composta por IA**: recorte da pessoa, tratamento/geração de fundo via
  Gemini ("Nano Banana"), com fallback local (Pillow) caso a chave de IA não esteja
  configurada, então o pipeline nunca trava por falta dela.
- **Título, descrição e hashtags** gerados por LLM, prontos para colar na publicação.
- **Marca d'água opcional**, aplicada por decisão explícita a cada execução (nunca por
  default silencioso).
- **Fila de revisão**: cada execução gera um manifesto (`manifest.json`) e um
  `ready-to-post.txt` por clipe; rodar de novo sobre o mesmo vídeo gera clipes **novos**,
  sem repetir trechos já usados.

O **aplicativo desktop** (`app/`) é o jeito principal de usar o Clipador: baixe o
instalador nas [Releases](https://github.com/J-Pster/pster-cliping/releases), instale
com um clique, sem precisar de Python nem terminal, e ele se atualiza sozinho. O mesmo
motor (`engine/`) tambem pode ser usado **direto pela CLI Python**, util pra
desenvolvimento ou automação.

## Como funciona (arquitetura)

```
YouTube / arquivo local
        │
        ▼
┌───────────────────┐   transcrição, seleção de trechos, corte, reenquadro,
│  engine (Python)  │   legenda, thumbnail, título/descrição/hashtags
└─────────▲─────────┘   roda como CLI, sem servidor próprio
          │  chama o engine como subprocesso (nunca reimplementa a lógica dele)
┌─────────┴─────────┐
│   app (Electron)   │  interface desktop: New Clip, Rebrand, Settings, editor de KB
└────────────────────┘  ja vem com Python + engine + ffmpeg embutidos
```

- **`engine/`** é a única parte que sabe transcrever, cortar, reenquadrar, legendar e
  gerar thumbnail/metadados. Roda standalone pela linha de comando, e é tratado como
  caixa-preta pelo `app/`: nada dessa lógica é reimplementada em TypeScript.
- **`app/`** é o aplicativo desktop Electron, o produto distribuível. O instalador
  embute um runtime Python portátil com as dependências do engine já instaladas, mais
  ffmpeg, então uma pessoa sem conhecimento técnico consegue instalar e usar sem
  Python, sem terminal e sem configuração manual. Se atualiza sozinho via GitHub
  Releases.

## Estrutura do repositório

```
pster-cliping/
├── engine/            # pipeline Python (transcrição → corte → legenda → thumbnail → metadados)
│   ├── src/clipador/  # código do pipeline, ver engine/CLAUDE.md para o layout completo
│   ├── kb/             # base de conhecimento por categoria de conteúdo
│   └── README.md        # como instalar e rodar o engine, guia completo de CLI
├── app/               # aplicativo desktop Electron, o produto distribuível
│   ├── scripts/        # build-python-runtime.ps1, fetch-ffmpeg.ps1 (runtime embutido)
│   └── README.md
├── .github/workflows/ # release.yml: builda e publica o instalador ao subir uma tag
├── .docs/decisions/   # decisões técnicas com a evidência que as sustenta
└── LICENSE            # PolyForm Noncommercial 1.0.0
```

Cada pasta de código tem seu próprio `README.md` (instalação e uso) e `CLAUDE.md`
(stack, layout interno e decisões técnicas vinculantes daquela parte). Este README da
raiz é o ponto de entrada; para detalhes profundos de qualquer parte, vá direto no
README/CLAUDE.md dela.

## Pré-requisitos

| Ferramenta | Para quê | Obrigatório para |
| --- | --- | --- |
| Nada | só instalar e usar o app | o aplicativo desktop (`.exe` das Releases) |
| **Python >= 3.11** | roda o engine | rodar a CLI direto, ou o `app/` em modo dev |
| **ffmpeg** no PATH, compilado com **libass** | corte, reenquadro, burn-in de legenda | engine (CLI/dev; ja vem embutido no app desktop) |
| **Node.js 24** e **npm** | buildar/rodar o app Electron a partir do codigo-fonte | `app/` em modo dev, ou pra buildar o instalador voce mesmo |
| GPU CUDA | opcional, só se optar por transcrição local (`whisperx`/`faster-whisper`) | nada por padrão: a config default roda 100% em CPU/nuvem |

## Instalação e primeira execução

### 1. Aplicativo desktop (recomendado)

Baixe o instalador mais recente nas
[Releases](https://github.com/J-Pster/pster-cliping/releases), rode (um clique, sem
pedir admin) e abra o Clipador pelo atalho na Area de Trabalho/Menu Iniciar. Preencha
suas chaves de API de IA na tela **Settings** e já pode gerar clipes. Detalhes do
runtime embutido e do auto-update em [`app/README.md`](app/README.md).

### 2. Rodar o engine diretamente (CLI)

Pra desenvolvimento ou automação, sem o aplicativo desktop:

```bash
git clone https://github.com/J-Pster/pster-cliping.git
cd pster-cliping/engine
pip install -e ".[video,cloud-transcribe,thumbnail-ai]"
cp .env.example .env
# preencha ELEVENLABS_API_KEY e CLAUDE_CODE_OAUTH_TOKEN (ou ANTHROPIC_API_KEY) no .env

python -m clipador.cli "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  --category politico_pessoa \
  --watermark off
```

Os clipes saem em `engine/output/<video_id>_<titulo>/`, junto com thumbnail, legenda
queimada, metadados e um `ready-to-post.txt` por clipe. Guia completo de instalação
(extras opcionais, GPU, fontes) e de uso (todas as flags) em
[`engine/README.md`](engine/README.md).

## Variáveis de ambiente

Nenhuma credencial fica hardcoded em código: tudo vem de `.env`. O
`engine/.env.example` documenta cada variável linha a linha; resumo das mais
importantes:

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `ELEVENLABS_API_KEY` | **sim**, por padrão | transcrição via ElevenLabs Scribe v2 (backend default; sem a chave o pipeline falha alto, de propósito, ver [`.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md`](.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md)) |
| `CLAUDE_CODE_OAUTH_TOKEN` | sim (modo `oauth`, default) | token gerado com `claude setup-token`, consome cota da assinatura Claude Pro/Max |
| `ANTHROPIC_API_KEY` | sim (se `CLIPADOR_LLM_AUTH_MODE=api_key`) | cobrança pay-per-use direto na API Anthropic |
| `GEMINI_API_KEY` | opcional | thumbnail com IA (sem ela, cai para tratamento local via Pillow) e LLM de texto se `CLIPADOR_TEXT_LLM_PROVIDER=gemini` |
| `CLIPADOR_TEXT_LLM_PROVIDER` | opcional (`claude` default) | `claude` ou `gemini`, LLM usado nas etapas de texto |
| `CLIPADOR_LLM_AUTH_MODE` | opcional (`oauth` default) | `oauth` ou `api_key`, só importa com `CLIPADOR_TEXT_LLM_PROVIDER=claude` |
| `HUGGINGFACE_TOKEN` | opcional | diarização real no backend local `whisperx --diarize` |
| `ASSEMBLYAI_API_KEY` | opcional | só para `--transcriber assemblyai` |
| `BUFFER_API_KEY` + `BUFFER_CHANNEL_<GRUPO>_<PLATAFORMA>` | opcional | publicação automática dos clipes aprovados via [Buffer](https://buffer.com) (`clipador-publish`) |

## Comandos úteis por parte do projeto

```bash
# engine (Python) — da pasta engine/
python -m pytest tests/ -q                     # suíte offline, sem rede/ffmpeg real
python -m clipador.cli --help                   # lista completa de flags, sempre atual
python scripts/run_test_video.py                # ponta a ponta com o vídeo de teste

# app (Electron) — da pasta app/
npm run dev                                       # app + hot reload
npm run build                                     # typecheck + build de produção
npm run dist                                      # builda o instalador Windows localmente (precisa rodar runtime:all antes)
```

## Documentação adicional

- [`engine/README.md`](engine/README.md) — guia completo de instalação e uso da CLI (todas as flags, extras opcionais, presets de legenda).
- [`engine/CLAUDE.md`](engine/CLAUDE.md) — stack, layout interno e decisões técnicas vinculantes do engine.
- [`app/README.md`](app/README.md) — setup de dev do app desktop, runtime embutido, empacotamento e auto-update.
- [`.docs/decisions/`](.docs/decisions) — registros de decisão com a evidência por trás de escolhas não óbvias (ex: por que a transcrição usa ElevenLabs Scribe v2 e não um modelo local).

## Licença

Este projeto está sob a [PolyForm Noncommercial License 1.0.0](./LICENSE): uso pessoal e
não comercial é livre; uso comercial requer autorização direta do autor
([Joao Pster](https://github.com/J-Pster)).
