# app

Aplicativo desktop (Electron) do Clipador. Antes era so um wrapper visual em volta de
um engine Python que a pessoa tinha que instalar e configurar manualmente; agora **o
app e o produto**: o instalador embute Python + todas as dependencias do engine +
ffmpeg, a pessoa baixa, instala com um clique e usa, sem terminal, sem instalar Python,
sem saber que existe um engine por baixo.

Este README cobre a parte Electron (`app/`). Para a stack, o layout e os comandos do
pipeline Python que ela orquestra, veja `../engine/README.md` e `../engine/CLAUDE.md`
(o engine continua sendo tratado como caixa-preta: nada da logica dele e reimplementada
aqui, ver `../CLAUDE.md`).

## Duas formas de rodar isto

1. **Desenvolvimento** (`npm run dev`): usa o checkout do monorepo, exatamente como
   antes. Requer o engine ja preparado (venv Python com as deps instaladas, ver
   `../engine/README.md` secoes 1 e 2) - o app so chama o `python`/`clipador` desse
   venv, nao instala nem gerencia nada.
2. **Instalador distribuido** (`.exe` gerado por `npm run dist`/`npm run release`, ou
   baixado de uma [Release do GitHub](https://github.com/J-Pster/pster-cliping/releases)):
   Python + engine + ffmpeg ja vem dentro do `.exe`, ninguem precisa instalar nada
   disso. Veja "Empacotamento" abaixo.

Qual codigo roda em qual caso e resolvido em runtime por
[`src/main/runtime-paths.ts`](src/main/runtime-paths.ts): `app.isPackaged` decide se
usa o Python/engine/ffmpeg embutidos nos `resources/` do app instalado, ou o checkout
`../engine` de sempre.

## Pre-requisitos (dev)

- **Node 24** e **npm**.
- **O engine ja preparado**: venv Python criado e dependencias instaladas (`pip install
  -e ".[video,cloud-transcribe,thumbnail-ai]"` ou equivalente), seguindo
  `../engine/README.md` secoes 1 e 2.

## Rodar em desenvolvimento

```bash
npm install
npm run dev
```

`npm run dev` sobe o processo main do Electron e o servidor Vite do renderer com hot
reload, e abre a janela do app.

## Build (typecheck + bundle JS)

```bash
npm run build
```

Roda o typecheck do TypeScript (main, preload e renderer, via `tsc --noEmit`) e depois
o build de producao do `electron-vite` (saida em `app/out/`). `npm run build` falha se
houver qualquer erro de tipo.

`npm run preview` roda o build de producao localmente, e `npm run typecheck` roda so a
checagem de tipos sem buildar.

## Empacotamento (gerar o `.exe` distribuivel)

Alem do `npm run build` (JS), o instalador precisa de um runtime Python portatil com o
engine instalado dentro, mais um ffmpeg estatico. Dois scripts PowerShell montam isso a
partir do zero (baixam da internet, nao dependem de nada ja instalado na maquina):

```bash
npm run runtime:python   # baixa o Python 3.11 embeddable, instala pip + clipador[video,cloud-transcribe,thumbnail-ai]
npm run runtime:ffmpeg   # baixa um build estatico do ffmpeg (BtbN, com libass)
# ou os dois de uma vez:
npm run runtime:all
```

Isso gera `app/resources/python/`, `app/resources/engine/` (copia read-only de kb/ e
assets/fonts/) e `app/resources/ffmpeg/` - **nao versionados** (`.gitignore`), pesados
(alguns GB por causa de torch/opencv/mediapipe/whisperx) e demorados pra baixar. Rode
de novo sempre que as deps do engine mudarem.

Com os `resources/` prontos:

```bash
npm run dist       # gera o instalador em app/dist/, sem publicar em lugar nenhum
npm run release    # gera E publica como asset de uma GitHub Release (precisa de GH_TOKEN)
```

O instalador e um NSIS "one click": a pessoa da run e ja esta instalado (por usuario,
sem pedir admin, sem dialogo de "avancar/avancar"), com atalho no Desktop e no menu
Iniciar. `deleteAppDataOnUninstall: false` garante que desinstalar nao apaga a pasta de
trabalho do usuario (kb editada, `.env` com as chaves de API, watermark configurada).

Configuracao completa em [`electron-builder.yml`](electron-builder.yml).

## Publicar uma release (fluxo normal)

Nao precisa rodar `npm run release` na sua maquina: o workflow
[`.github/workflows/release.yml`](../.github/workflows/release.yml) builda tudo (JS +
runtime Python + ffmpeg) num runner `windows-latest` e publica o instalador como asset
de uma GitHub Release, sozinho, quando voce sobe uma tag `vX.Y.Z`:

```bash
git tag v0.2.0
git push origin v0.2.0
```

## Como funciona o auto-update

O app usa [`electron-updater`](https://www.electron.build/auto-update), que so age em
build empacotado (`app.isPackaged`, ver [`src/main/updater.ts`](src/main/updater.ts)):
ao abrir, checa a Release mais recente deste repo no GitHub, baixa em segundo plano se
houver uma versao nova, e mostra um aviso pra reiniciar quando o download terminar
(`UpdateBanner`, no topo da janela). Sem clicar em nada tambem funciona: o update fica
pronto pra instalar no proximo fechar/abrir do app (`autoInstallOnAppQuit`).

Alternativa manual, sempre disponivel: baixar o instalador mais novo direto da pagina
de [Releases](https://github.com/J-Pster/pster-cliping/releases) e rodar de novo (o
NSIS one-click atualiza a instalacao existente).

## Onde ficam os dados do usuario (persistem entre updates)

A pasta de instalacao (`resources/`) e **substituida inteira** a cada auto-update -
nada gravado la sobrevive. Por isso tudo que o usuario edita ou configura fica em
`app.getPath('userData')` (`%APPDATA%/Clipador` no Windows), que o updater nunca toca:

- `clipador-config.json`, `clipador-features.json`: preferencias e configuracao de
  features (marca d'agua, propaganda eleitoral).
- `engine-workspace/`: pasta de trabalho gravavel do engine em producao - `kb/` (copia
  editavel, semeada da copia read-only dos `resources/` na primeira execucao, nunca
  sobrescrita depois), `.env` (chaves de API preenchidas na tela Settings) e `output/`
  (clipes gerados).
- `watermark/`: imagem-fonte e PNGs ja "assados" da marca d'agua.

## Primeiro uso

1. Preencha as chaves de API de IA na tela **Settings**: sao as mesmas variaveis
   documentadas em `../engine/.env.example` (provedor de LLM de texto, autenticacao
   Claude, ElevenLabs, Gemini, YouTube, HuggingFace, AssemblyAI, Buffer, etc.), so que
   editadas por formulario em vez de texto puro num `.env`. No build empacotado nao ha
   mais campo de "pasta do engine"/"Python" pra configurar - isso ja vem pronto.
2. Salve as configuracoes.
3. Use as telas **New Clip** (gera clipes a partir de uma URL do YouTube ou arquivo
   local) ou **Rebrand** (re-brandeia em lote uma pasta de clipes curtos ja existentes)
   para rodar o engine.
