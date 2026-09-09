import { useEffect, useState } from 'react'
import type { ClipadorCategory, KbDoc, KbSection, KbSnapshot } from '@shared/ipc-contract'

const CATEGORY_OPTIONS: { value: ClipadorCategory; label: string }[] = [
  { value: 'politico_pessoa', label: 'Politico / pessoa publica' },
  { value: 'jogos', label: 'Jogos' },
  { value: 'livro_audiobook', label: 'Livro / audiobook' }
]

const SECTION_LABEL: Record<KbSection, string> = {
  core: 'Dossie (core)',
  topics: 'Topicos'
}

const SECTION_HINT: Record<KbSection, string> = {
  core: 'Injetado inteiro no prompt de selecao, em toda rodada. Poucos arquivos, curtos.',
  topics: 'Busca por palavra-chave sob demanda, um arquivo por assunto. Pode ter muitos.'
}

function newDocTemplate(): string {
  return '# Titulo do documento\n\nConteudo em markdown aqui.\n'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface EditorState {
  section: KbSection
  /** Vazio quando e um documento novo (ainda sem nome confirmado). */
  originalFilename: string
  filename: string
  content: string
}

export default function KnowledgeBaseRoute(): React.JSX.Element {
  const [category, setCategory] = useState<ClipadorCategory>('politico_pessoa')
  const [snapshot, setSnapshot] = useState<KbSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [addingSource, setAddingSource] = useState(false)

  async function reload(): Promise<void> {
    setLoading(true)
    setLoadError(null)
    try {
      const loaded = await window.api.kb.list(category)
      setSnapshot(loaded)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setEditor(null)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category])

  function openNewDoc(section: KbSection): void {
    setActionError(null)
    setEditor({ section, originalFilename: '', filename: '', content: newDocTemplate() })
  }

  function openEditDoc(section: KbSection, doc: KbDoc): void {
    setActionError(null)
    setEditor({ section, originalFilename: doc.filename, filename: doc.filename, content: doc.content })
  }

  async function saveEditor(): Promise<void> {
    if (!editor) return
    if (!editor.filename.trim()) {
      setActionError('Da um nome de arquivo pro documento.')
      return
    }
    setSaving(true)
    setActionError(null)
    try {
      await window.api.kb.saveDoc(category, editor.section, editor.filename, editor.content)
      setEditor(null)
      await reload()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  async function deleteDoc(section: KbSection, filename: string): Promise<void> {
    if (!window.confirm(`Excluir "${filename}"? Nao da pra desfazer.`)) return
    setActionError(null)
    try {
      await window.api.kb.deleteDoc(category, section, filename)
      if (editor?.section === section && editor.originalFilename === filename) {
        setEditor(null)
      }
      await reload()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    }
  }

  async function addSource(): Promise<void> {
    setAddingSource(true)
    setActionError(null)
    try {
      await window.api.kb.addSource(category)
      await reload()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    } finally {
      setAddingSource(false)
    }
  }

  async function removeSource(filename: string): Promise<void> {
    if (!window.confirm(`Remover "${filename}" das fontes?`)) return
    setActionError(null)
    try {
      await window.api.kb.removeSource(category, filename)
      await reload()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    }
  }

  function renderSection(section: KbSection, docs: KbDoc[]): React.JSX.Element {
    return (
      <div className="lu-card">
        <div className="lu-kb-section-header">
          <div>
            <h2 className="lu-section-title">{SECTION_LABEL[section]}</h2>
            <p className="lu-hint">{SECTION_HINT[section]}</p>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => openNewDoc(section)}>
            + Novo documento
          </button>
        </div>

        {docs.length === 0 ? (
          <p className="lu-hint">Nenhum documento ainda.</p>
        ) : (
          <ul className="lu-kb-doc-list">
            {docs.map((doc) => (
              <li key={doc.filename} className="lu-kb-doc-row">
                <div className="lu-kb-doc-row__info">
                  <span className="lu-kb-doc-row__title">{doc.title}</span>
                  <span className="lu-kb-doc-row__filename">{doc.filename}.md</span>
                </div>
                <div className="lu-kb-doc-row__actions">
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    onClick={() => openEditDoc(section, doc)}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => deleteDoc(section, doc.filename)}
                  >
                    Excluir
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return (
    <div className="lu-stack">
      <div className="lu-card">
        <h2 className="lu-section-title">Categoria</h2>
        <div className="lu-field">
          <select
            className="lu-control"
            value={category}
            onChange={(event) => setCategory(event.target.value as ClipadorCategory)}
          >
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {snapshot && <p className="lu-hint">Pasta: {snapshot.root}</p>}
        </div>
      </div>

      {loadError && <div className="lu-banner lu-banner--error">Falha ao carregar: {loadError}</div>}
      {actionError && <div className="lu-banner lu-banner--error">{actionError}</div>}

      {loading ? (
        <p className="lu-hint">Carregando base de conhecimento...</p>
      ) : (
        snapshot && (
          <>
            {renderSection('core', snapshot.core)}
            {renderSection('topics', snapshot.topics)}

            <div className="lu-card">
              <div className="lu-kb-section-header">
                <div>
                  <h2 className="lu-section-title">Fontes (arquivos de referencia)</h2>
                  <p className="lu-hint">
                    PDFs e outros arquivos brutos usados como material de apoio. Nao entram no prompt
                    automaticamente, ficam guardados junto do dossie.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={addSource}
                  disabled={addingSource}
                >
                  {addingSource ? 'Adicionando...' : '+ Adicionar arquivo'}
                </button>
              </div>

              {snapshot.sources.length === 0 ? (
                <p className="lu-hint">Nenhuma fonte ainda.</p>
              ) : (
                <ul className="lu-kb-doc-list">
                  {snapshot.sources.map((source) => (
                    <li key={source.filename} className="lu-kb-doc-row">
                      <div className="lu-kb-doc-row__info">
                        <span className="lu-kb-doc-row__title">{source.filename}</span>
                        <span className="lu-kb-doc-row__filename">{formatBytes(source.sizeBytes)}</span>
                      </div>
                      <div className="lu-kb-doc-row__actions">
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => removeSource(source.filename)}
                        >
                          Remover
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )
      )}

      {editor && (
        <div className="lu-kb-editor-overlay" role="dialog" aria-modal="true">
          <div className="lu-kb-editor">
            <h2 className="lu-section-title">
              {editor.originalFilename ? 'Editar documento' : 'Novo documento'} -{' '}
              {SECTION_LABEL[editor.section]}
            </h2>
            <div className="lu-field">
              <label className="lu-label">Nome do arquivo (sem .md)</label>
              <input
                className="lu-control"
                type="text"
                value={editor.filename}
                placeholder="ex. 10-novo-topico"
                disabled={Boolean(editor.originalFilename)}
                onChange={(event) => setEditor({ ...editor, filename: event.target.value })}
              />
              <p className="lu-hint">
                A ordem de exibicao segue ordem alfabetica do nome do arquivo, por isso o prefixo
                numerico (00, 05, 10...).
              </p>
            </div>
            <div className="lu-field">
              <label className="lu-label">Conteudo (markdown)</label>
              <textarea
                className="lu-control lu-kb-editor__textarea"
                value={editor.content}
                onChange={(event) => setEditor({ ...editor, content: event.target.value })}
              />
              <p className="lu-hint">
                A primeira linha "# Titulo" vira o titulo exibido nesta tela e o cabecalho usado pelo
                engine.
              </p>
            </div>
            <div className="lu-kb-editor__actions">
              <button type="button" className="btn btn-secondary" onClick={() => setEditor(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={saveEditor}
                disabled={saving}
              >
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
