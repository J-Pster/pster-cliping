# Clipador

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](engine/pyproject.toml)
[![NestJS](https://img.shields.io/badge/backend-NestJS%2011-E0234E?logo=nestjs&logoColor=white)](backend/package.json)
[![Angular](https://img.shields.io/badge/frontend-Angular%2021-DD0031?logo=angular&logoColor=white)](frontend/package.json)
[![Electron](https://img.shields.io/badge/local--use-Electron-47848F?logo=electron&logoColor=white)](local-use/package.json)

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
  - [1. Clonar e configurar variáveis de ambiente](#1-clonar-e-configurar-variáveis-de-ambiente)
  - [2. Subir backend + banco (Docker)](#2-subir-backend--banco-docker)
  - [3. Rodar o frontend](#3-rodar-o-frontend)
  - [4. Rodar o engine diretamente (CLI)](#4-rodar-o-engine-diretamente-cli)
  - [5. Alternativa sem instalar nada de código: a GUI desktop](#5-alternativa-sem-instalar-nada-de-código-a-gui-desktop)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Uso: dois jeitos de gerar clipes](#uso-dois-jeitos-de-gerar-clipes)
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

O mesmo motor (`engine/`) pode ser usado de duas formas:

1. **Como parte do SaaS completo** (`backend` + `frontend`): upload pela web, fila de
   jobs, autenticação, histórico de clipes por conta.
2. **Standalone, via GUI desktop** (`local-use/`) ou **direto pela CLI Python**, sem
   precisar subir backend nem frontend, ideal para rodar na própria máquina.

## Como funciona (arquitetura)

```
YouTube / arquivo local
        │
        ▼
┌───────────────────┐   transcrição, seleção de trechos, corte, reenquadro,
│  engine (Python)  │   legenda, thumbnail, título/descrição/hashtags
└─────────▲─────────┘   roda como CLI, sem servidor próprio
          │  orquestra via subprocesso/fila (nunca reimplementa a lógica do engine)
┌─────────┴─────────┐
│ backend (NestJS)  │   jobs, usuários, clipes, autenticação (Cognito), billing
└─────────▲─────────┘   Postgres via TypeORM
          │  HTTP
┌─────────┴─────────┐
│ frontend (Angular) │  upload do vídeo, progresso do job, revisão/exportação
└────────────────────┘
```

- **`engine/`** é a única parte que sabe transcrever, cortar, reenquadrar, legendar e
  gerar thumbnail/metadados. É tratado como **caixa-preta** pelo backend: nada dessa
  lógica é reimplementada em TypeScript.
- **`backend/`** é fino em orquestração: recebe o pedido, chama o engine, persiste
  resultado, nunca decide sozinho o que é "um bom corte" ou "uma boa thumbnail".
- **`frontend/`** só fala com o backend por HTTP, nunca chama o engine diretamente.
- **`local-use/`** é um caminho paralelo que pula backend e frontend inteiramente: uma
  janela Electron chama o `engine` local (o mesmo código Python), pensada para quem quer
  usar o Clipador sem operar um servidor.

## Estrutura do repositório

```
pster-cliping/
├── engine/            # pipeline Python (transcrição → corte → legenda → thumbnail → metadados)
│   ├── src/clipador/  # código do pipeline, ver engine/CLAUDE.md para o layout completo
│   ├── kb/             # base de conhecimento por categoria de conteúdo
│   └── README.md        # como instalar e rodar o engine, guia completo de CLI
├── backend/           # API NestJS 11 (TypeORM + PostgreSQL)
│   └── README.md
├── frontend/          # SPA Angular 21 (standalone components)
│   └── README.md
├── local-use/         # GUI desktop Electron, wrapper local do engine
│   └── README.md
├── .docs/decisions/   # decisões técnicas com a evidência que as sustenta
├── docker-compose.yml # Postgres + backend, dev local
├── DESIGN.md          # sistema de design usado pelo frontend
└── LICENSE            # PolyForm Noncommercial 1.0.0
```

Cada pasta de código tem seu próprio `README.md` (instalação e uso) e `CLAUDE.md`
(stack, layout interno e decisões técnicas vinculantes daquela parte). Este README da
raiz é o ponto de entrada; para detalhes profundos de qualquer parte, vá direto no
README/CLAUDE.md dela.

## Pré-requisitos

| Ferramenta | Para quê | Obrigatório para |
| --- | --- | --- |
| **Docker** e **Docker Compose** | sobe Postgres + backend em dev | usar o SaaS completo (backend/frontend) |
| **Node.js 24** e **npm** | backend (NestJS) e frontend (Angular) | backend/frontend/local-use |
| **Python >= 3.11** | roda o engine | qualquer geração de clipe (SaaS, CLI ou GUI) |
| **ffmpeg** no PATH, compilado com **libass** | corte, reenquadro, burn-in de legenda | engine |
| **AWS CLI configurado (SSO)** | Cognito/Secrets Manager em dev | backend (autenticação real, sem fallback local) |
| GPU CUDA | opcional, só se optar por transcrição local (`whisperx`/`faster-whisper`) | nada por padrão: a config default roda 100% em CPU/nuvem |

## Instalação e primeira execução

### 1. Clonar e configurar variáveis de ambiente

```bash
git clone https://github.com/J-Pster/pster-cliping.git
cd pster-cliping
```

Copie o `.env.example` de cada pasta que for usar e preencha as chaves. Nenhum `.env` é
versionado (ver `.gitignore`); só os `.env.example` de cada pasta ficam no repositório.

```bash
cp .env.example .env                    # raiz: Postgres local, perfil AWS, Cognito
cp backend/.env.example backend/.env     # backend: hoje só a porta HTTP (o resto vem do docker-compose)
cp engine/.env.example engine/.env       # engine: chaves de transcrição/LLM (ver tabela abaixo)
```

### 2. Subir backend + banco (Docker)

Da raiz do repositório:

```bash
docker compose up -d
```

Sobe Postgres (porta `5433` no host) e o backend NestJS (porta `3000`), com hot-reload
do código em `backend/src`. O container do backend monta `~/.aws` (somente leitura) e
usa o perfil definido em `AWS_PROFILE` para autenticar de verdade contra
Cognito/Secrets Manager, sem fallback local para segredo de produção.

```bash
docker logs cortepolitico-backend -f   # acompanhar os logs
```

### 3. Rodar o frontend

```bash
cd frontend
npm install
npm start
```

Abre em `http://localhost:4200`, consumindo o backend em `http://localhost:3000`.

### 4. Rodar o engine diretamente (CLI)

O engine não depende do backend/frontend para funcionar: pode ser chamado direto pela
linha de comando. Guia completo de instalação (extras opcionais, GPU, fontes) e de uso
(todas as flags) em [`engine/README.md`](engine/README.md); resumo mínimo:

```bash
cd engine
pip install -e ".[video,cloud-transcribe,thumbnail-ai]"
cp .env.example .env   # se ainda não fez no passo 1
# preencha ELEVENLABS_API_KEY e CLAUDE_CODE_OAUTH_TOKEN (ou ANTHROPIC_API_KEY) no .env

python -m clipador.cli "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  --category politico_pessoa \
  --watermark off
```

Os clipes saem em `engine/output/<video_id>_<titulo>/`, junto com thumbnail, legenda
queimada, metadados e um `ready-to-post.txt` por clipe.

### 5. Alternativa sem instalar nada de código: a GUI desktop

`local-use/` é um app Electron que roda o mesmo engine por trás de uma interface
gráfica, sem precisar de terminal, backend ou frontend. Útil para uso pessoal na própria
máquina. Requer o engine já instalado (passo 4). Detalhes em
[`local-use/README.md`](local-use/README.md):

```bash
cd local-use
npm install
npm run dev
```

## Variáveis de ambiente

Nenhuma credencial fica hardcoded em código: tudo vem de `.env` (dev) ou, em produção, do
AWS Secrets Manager. Cada pasta documenta as suas variáveis linha a linha no próprio
`.env.example`; resumo das mais importantes:

### Raiz (`.env`, usada pelo `docker-compose.yml`)

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | sim | credenciais do Postgres local, qualquer valor serve em dev |
| `AWS_PROFILE` | sim (backend real) | perfil AWS CLI/SSO montado no container do backend |
| `AWS_REGION` | sim | região AWS do projeto |
| `COGNITO_USER_POOL_ID` / `COGNITO_CLIENT_ID` | sim (auth) | User Pool do Cognito provisionado na conta AWS |
| `SECRETS_MANAGER_SECRET_ID` | sim (auth) | segredo com as chaves de API usadas pelo backend |

### `engine/.env`

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `ELEVENLABS_API_KEY` | **sim**, por padrão | transcrição via ElevenLabs Scribe v2 (backend default; sem a chave o pipeline falha alto, de propósito, ver [`.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md`](.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md)) |
| `CLAUDE_CODE_OAUTH_TOKEN` | sim (modo `oauth`, default) | token gerado com `claude setup-token`, consome cota da assinatura Claude Pro/Max |
| `ANTHROPIC_API_KEY` | sim (se `CLIPADOR_LLM_AUTH_MODE=api_key`) | cobrança pay-per-use direto na API Anthropic |
| `GEMINI_API_KEY` | opcional | thumbnail com IA (sem ela, cai para tratamento local via Pillow) e LLM de texto se `CLIPADOR_TEXT_LLM_PROVIDER=gemini` |
| `CLIPADOR_TEXT_LLM_PROVIDER` | opcional (`claude` default) | `claude` ou `gemini`, LLM usado nas etapas de texto |
| `CLIPADOR_LLM_AUTH_MODE` | opcional (`oauth` default) | `oauth` ou `api_key`, só importa com `CLIPADOR_TEXT_LLM_PROVIDER=claude` |
| `YOUTUBE_API_KEY` | opcional, hoje não usada pelo pipeline principal | YouTube Data API v3, ver nota em `engine/README.md` |
| `HUGGINGFACE_TOKEN` | opcional | diarização real no backend local `whisperx --diarize` |
| `ASSEMBLYAI_API_KEY` | opcional | só para `--transcriber assemblyai` |
| `BUFFER_API_KEY` + `BUFFER_CHANNEL_<GRUPO>_<PLATAFORMA>` | opcional | publicação automática dos clipes aprovados via [Buffer](https://buffer.com) (`clipador-publish`) |

### `backend/.env`

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `PORT` | não (default `3000`) | porta HTTP do backend; via `docker compose` já vem definida pelo serviço |

## Uso: dois jeitos de gerar clipes

**Pelo SaaS (backend + frontend):** suba os dois (passos 2 e 3), acesse o frontend,
faça upload do vídeo ou cole o link do YouTube, acompanhe o progresso do job e revise os
clipes gerados na fila antes de baixar/publicar.

**Direto pela CLI ou pela GUI desktop:** rode `engine` isolado (passo 4) ou `local-use`
(passo 5). Mesmo motor, sem precisar de conta nem servidor. Bom para uso pessoal ou para
depurar o pipeline sem o resto da stack.

## Comandos úteis por parte do projeto

```bash
# engine (Python) — da pasta engine/
python -m pytest tests/ -q                     # suíte offline, sem rede/ffmpeg real
python -m clipador.cli --help                   # lista completa de flags, sempre atual
python scripts/run_test_video.py                # ponta a ponta com o vídeo de teste

# backend (NestJS) — da pasta backend/
npm run start:dev                                # dev sem Docker, watch mode
npm run build                                     # nest build
npm run test                                      # Jest

# frontend (Angular) — da pasta frontend/
npm start                                         # ng serve
npm run build                                     # build de produção
npm test                                          # testes unitários

# local-use (Electron) — da pasta local-use/
npm run dev                                       # app + hot reload
npm run build                                     # typecheck + build de produção
```

## Documentação adicional

- [`engine/README.md`](engine/README.md) — guia completo de instalação e uso da CLI (todas as flags, extras opcionais, presets de legenda).
- [`engine/CLAUDE.md`](engine/CLAUDE.md), [`backend/CLAUDE.md`](backend/CLAUDE.md), [`frontend/CLAUDE.md`](frontend/CLAUDE.md) — stack, layout interno e decisões técnicas vinculantes de cada parte.
- [`.docs/decisions/`](.docs/decisions) — registros de decisão com a evidência por trás de escolhas não óbvias (ex: por que a transcrição usa ElevenLabs Scribe v2 e não um modelo local).
- [`DESIGN.md`](DESIGN.md) — sistema de design (tokens, tipografia, cores) usado pelo frontend.

## Licença

Este projeto está sob a [PolyForm Noncommercial License 1.0.0](./LICENSE): uso pessoal e
não comercial é livre; uso comercial requer autorização direta do autor
([Joao Pster](https://github.com/J-Pster)).
