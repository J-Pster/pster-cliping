; Pagina extra do instalador NSIS (electron-builder), inserida depois de "escolher
; pasta" e antes de "instalar" (hook customPageAfterChangeDir, ver
; node_modules/app-builder-lib/templates/nsis/assistedInstaller.nsh:42).
;
; A base de conhecimento da categoria politico_pessoa (dossie em kb/core,
; topicos em kb/topics, fontes em kb/sources) sempre vai dentro do instalador,
; junto do resto de resources/engine (ver electron-builder.yml extraResources).
; O checkbox aqui so decide se ela fica no disco apos a extracao: se desmarcado,
; customInstall remove a pasta logo depois de installApplicationFiles (ver
; node_modules/app-builder-lib/templates/nsis/installSection.nsh).
;
; O app nunca quebra com a pasta ausente: ensureWorkDirSeeded (runtime-paths.ts)
; copia kb/ inteiro no primeiro boot, so o que existir; e kb.ts (readDocsFrom /
; readSourcesFrom) faz existsSync antes de ler, retornando lista vazia se a
; categoria nao tiver arquivos. O usuario pode preencher na tela de Base de
; Conhecimento do app depois, manualmente.

!include nsDialogs.nsh

; So existem no passo do instalador: o uninstaller compila este mesmo arquivo
; (BUILD_UNINSTALLER definido) sem usar a pagina/macro abaixo, e o makensis do
; electron-builder trata "variavel nunca lida" (warning 6001) como erro de build.
!ifndef BUILD_UNINSTALLER
  Var InstallKbCheckbox
  Var InstallKb
!endif

!macro customPageAfterChangeDir
  Page custom kbOptionsPageShow kbOptionsPageLeave

  Function kbOptionsPageShow
    !insertmacro MUI_HEADER_TEXT "Base de conhecimento" "Escolha o que instalar junto com o Pster Clipping"

    nsDialogs::Create 1018
    Pop $0

    ${NSD_CreateCheckbox} 0u 0u 300u 20u "Instalar base de conhecimento (dossie politico-pessoa)"
    Pop $InstallKbCheckbox
    ${NSD_SetState} $InstallKbCheckbox ${BST_CHECKED}

    ${NSD_CreateLabel} 0u 25u 300u 60u "Inclui o dossie, os topicos e as fontes usados pelo engine para gerar titulos, descricoes e cortes na categoria politico-pessoa. Desmarque se voce nao for usar essa categoria; da pra adicionar o conteudo manualmente depois, na tela de Base de Conhecimento do app."
    Pop $1

    nsDialogs::Show
  FunctionEnd

  Function kbOptionsPageLeave
    ${NSD_GetState} $InstallKbCheckbox $InstallKb
  FunctionEnd
!macroend

!macro customInstall
  ${if} $InstallKb == ${BST_UNCHECKED}
    RMDir /r "$INSTDIR\resources\engine\kb\politico_pessoa"
  ${endif}
!macroend
