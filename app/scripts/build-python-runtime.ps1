<#
.SYNOPSIS
  Monta o runtime Python portatil que vai dentro do app empacotado (resources/python)
  e a copia read-only de kb/ + assets/fonts/ (resources/engine), a partir do
  Python embeddable oficial + do checkout local de ../../engine.

  NAO precisa de Python nem venv ja instalado na maquina que roda este script (so
  precisa de rede pra baixar o embeddable + get-pip.py). Roda tanto localmente
  quanto no runner windows-latest do GitHub Actions (ver .github/workflows/release.yml).

.NOTES
  Download pesado (torch/opencv/mediapipe/whisperx do extra "video"): espere alguns
  minutos e alguns GB em disco. Rode de novo pra atualizar depois de mudar deps do
  engine (o script limpa resources/python e resources/engine antes de comecar).
#>

$ErrorActionPreference = 'Stop'

$PythonVersion = '3.11.9'
$PythonTag = 'python311'  # usado no nome do arquivo pythonXXX._pth dentro do embeddable

$AppRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $AppRoot
$EngineSrcDir = Join-Path $RepoRoot 'engine'
$ResourcesDir = Join-Path $AppRoot 'resources'
$PythonDir = Join-Path $ResourcesDir 'python'
$EngineOutDir = Join-Path $ResourcesDir 'engine'
$TmpDir = Join-Path $AppRoot '.runtime-tmp\python'

if (-not (Test-Path $EngineSrcDir)) {
    throw "engine/ nao encontrado em $EngineSrcDir. Rode este script de dentro do checkout do monorepo."
}

Write-Host "== Limpando runtime anterior =="
foreach ($dir in @($PythonDir, $EngineOutDir, $TmpDir)) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
New-Item -ItemType Directory -Force -Path $PythonDir, $EngineOutDir, $TmpDir | Out-Null

Write-Host "== Baixando Python $PythonVersion embeddable =="
$EmbedZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$EmbedZipPath = Join-Path $TmpDir 'python-embed.zip'
Invoke-WebRequest -Uri $EmbedZipUrl -OutFile $EmbedZipPath
Expand-Archive -Path $EmbedZipPath -DestinationPath $PythonDir -Force

Write-Host "== Habilitando site-packages no embeddable =="
$PthFile = Join-Path $PythonDir "$PythonTag._pth"
(Get-Content $PthFile) -replace '^#import site$', 'import site' | Set-Content $PthFile

Write-Host "== Instalando pip =="
$GetPipPath = Join-Path $TmpDir 'get-pip.py'
Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $GetPipPath
$PythonExe = Join-Path $PythonDir 'python.exe'
& $PythonExe $GetPipPath --no-compile --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw 'get-pip.py falhou' }

Write-Host "== Instalando o build backend (hatchling) direto, sem isolamento =="
# O embeddable nao tem o modulo `venv` (usado pelo pip pra criar o ambiente de build
# isolado default): sem isso, "pip install" de um pacote local (clipador, via
# pyproject.toml/hatchling) falha com "BackendUnavailable: Cannot import
# 'hatchling.build'". Instala o backend direto no ambiente e usa --no-build-isolation
# so pra esse pacote local; as outras deps (torch, opencv, mediapipe etc) ja vem como
# wheel pronto do PyPI, entao build isolation nao faz falta pra elas.
& $PythonExe -m pip install hatchling --no-compile --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw 'pip install do hatchling falhou' }

Write-Host "== Instalando clipador + cloud-transcribe + thumbnail-ai + CV/reenquadro (SEM whisperx/faster-whisper) =="
# O extra "video" do engine (pyproject.toml) junta duas coisas que nao tem nada a ver
# uma com a outra no mesmo grupo: (a) opencv/mediapipe/scenedetect/librosa, usados
# SEMPRE pelo reenquadro 9:16 e deteccao de rosto, e (b) faster-whisper/whisperx,
# transcricao LOCAL - um backend alternativo ao default (ElevenLabs Scribe v2, nuvem),
# que este app nunca usa (ver engine/CLAUDE.md: "toda transcricao usa Scribe v2 por
# padrao"). (b) e o que traz o torch inteiro (torch/torchaudio/torchvision +
# pyannote/lightning/optuna/transformers pra diarizacao) - sozinho isso e bem mais da
# metade dos arquivos do runtime inteiro. Instala so o subconjunto (a) explicitamente,
# em vez do extra "video" inteiro, pra nunca puxar torch. `whisper.py`/
# `whisperx_transcriber.py` importam faster_whisper/whisperx dentro de funcao (lazy),
# nao no topo do modulo, entao a ausencia deles NAO quebra o resto do engine - so
# quebraria se alguem escolhesse esses backends, e a UI do app nem oferece essa opcao
# (ver src/renderer/src/routes/NewClip.tsx, TranscriberBackend em ipc-contract.ts).
& $PythonExe -m pip install "$EngineSrcDir[cloud-transcribe,thumbnail-ai]" opencv-python mediapipe scenedetect librosa --no-build-isolation --no-compile --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw 'pip install do engine falhou' }

$TorchDir = Join-Path $PythonDir 'Lib\site-packages\torch'
if (Test-Path $TorchDir) {
    throw 'torch foi instalado mesmo assim - alguma dependencia nova esta puxando ele, investigar antes de continuar'
}

Write-Host "== Removendo pip/setuptools/wheel do runtime final =="
# So servem pra INSTALAR pacotes (usados ate aqui neste script). Nada no engine nem no
# app chama `pip` em runtime (o app so spawna `python -m clipador.cli`/`clipador.rebrand.cli`
# diretamente) - sao ~1100 arquivos de ferramenta de build que nunca rodam depois de
# pronto, so custam tempo de instalacao (Defender escaneando arquivo por arquivo) a toa.
$SitePackages = Join-Path $PythonDir 'Lib\site-packages'
Get-ChildItem $SitePackages -Directory -Filter 'pip' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Directory -Filter 'pip-*.dist-info' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Directory -Filter 'setuptools' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Directory -Filter 'setuptools-*.dist-info' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Directory -Filter '_distutils_hack' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Directory -Filter 'wheel' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Directory -Filter 'wheel-*.dist-info' | Remove-Item -Recurse -Force
Get-ChildItem $SitePackages -Filter 'distutils-precedence.pth' | Remove-Item -Force
$ScriptsDir = Join-Path $PythonDir 'Scripts'
Get-ChildItem $ScriptsDir -Filter 'pip*.exe' -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem $ScriptsDir -Filter 'wheel.exe' -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "== Copiando kb/, assets/ e .env.example (read-only, seed inicial) =="
Copy-Item -Recurse (Join-Path $EngineSrcDir 'kb') (Join-Path $EngineOutDir 'kb')
Copy-Item -Recurse (Join-Path $EngineSrcDir 'assets') (Join-Path $EngineOutDir 'assets')
Copy-Item (Join-Path $EngineSrcDir '.env.example') (Join-Path $EngineOutDir '.env.example')

if (Test-Path $TmpDir) { Remove-Item -Recurse -Force $TmpDir }

Write-Host "== OK: resources/python e resources/engine prontos =="
