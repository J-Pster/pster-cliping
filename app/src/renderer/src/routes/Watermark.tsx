import { useEffect, useState } from 'react'
import type { FeaturesConfig, WatermarkFormat, WatermarkFormatState } from '@shared/ipc-contract'
import WatermarkFormatEditor from '../components/WatermarkFormatEditor'
import { LONG_SAFE_ZONE, SHORT_SAFE_ZONE } from '@shared/watermarkSafeZone'

export default function WatermarkRoute(): React.JSX.Element {
  const [config, setConfig] = useState<FeaturesConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pickingImage, setPickingImage] = useState(false)
  const [removingImage, setRemovingImage] = useState(false)
  const [sourceImageUrl, setSourceImageUrl] = useState<string | null>(null)
  const [savingFormat, setSavingFormat] = useState<WatermarkFormat | null>(null)
  const [bakedShort, setBakedShort] = useState<string | null>(null)
  const [bakedLong, setBakedLong] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load(): Promise<void> {
      setLoading(true)
      setLoadError(null)
      try {
        const [loadedConfig, sourcePreview, shortPreview, longPreview] = await Promise.all([
          window.api.features.get(),
          window.api.watermark.readSourceImage(),
          window.api.watermark.readBakedImage('short'),
          window.api.watermark.readBakedImage('long')
        ])
        if (cancelled) return
        setConfig(loadedConfig)
        setSourceImageUrl(sourcePreview)
        setBakedShort(shortPreview)
        setBakedLong(longPreview)
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : String(error))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  async function persist(next: FeaturesConfig): Promise<void> {
    await window.api.features.save(next)
    setConfig(next)
  }

  async function pickSourceImage(): Promise<void> {
    if (!config) return
    setActionError(null)
    setPickingImage(true)
    try {
      const picked = await window.api.watermark.pickSourceImage()
      if (picked) {
        setSourceImageUrl(picked.previewDataUrl)
        await persist({ ...config, watermark: { ...config.watermark, sourceImagePath: picked.path } })
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    } finally {
      setPickingImage(false)
    }
  }

  async function removeSourceImage(): Promise<void> {
    if (!config) return
    if (!window.confirm("Remover a imagem-fonte da marca d'água?")) return
    setActionError(null)
    setRemovingImage(true)
    try {
      await window.api.watermark.removeSourceImage()
      setSourceImageUrl(null)
      await persist({ ...config, watermark: { ...config.watermark, sourceImagePath: null } })
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    } finally {
      setRemovingImage(false)
    }
  }

  function updateFormatState(format: WatermarkFormat, next: WatermarkFormatState): void {
    if (!config) return
    setConfig({ ...config, watermark: { ...config.watermark, [format]: next } })
  }

  async function saveFormat(format: WatermarkFormat, pngBytes: ArrayBuffer): Promise<void> {
    if (!config) return
    setActionError(null)
    setSavingFormat(format)
    try {
      const result = await window.api.watermark.saveBakedImage(format, pngBytes)
      if (format === 'short') {
        setBakedShort(result.previewDataUrl)
      } else {
        setBakedLong(result.previewDataUrl)
      }
      await persist(config)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    } finally {
      setSavingFormat(null)
    }
  }

  async function setEnabled(enabled: boolean): Promise<void> {
    if (!config) return
    setActionError(null)
    try {
      await persist({ ...config, watermark: { ...config.watermark, enabled } })
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error))
    }
  }

  if (loading) {
    return <p className="lu-hint">Carregando configurações de marca d'água...</p>
  }

  if (!config) {
    return <div className="lu-banner lu-banner--error">Falha ao carregar: {loadError}</div>
  }

  const { watermark } = config
  const bothBaked = Boolean(bakedShort) && Boolean(bakedLong)

  return (
    <div className="lu-stack">
      {loadError && <div className="lu-banner lu-banner--error">Falha ao carregar: {loadError}</div>}
      {actionError && <div className="lu-banner lu-banner--error">{actionError}</div>}

      <div className="lu-card">
        <h2 className="lu-section-title">Logo da marca d'água</h2>
        <p className="lu-hint">
          Envie a logo ou marca que você quer usar. Ela deve ter fundo transparente (PNG), o
          formato final (tamanho do quadro inteiro) é gerado abaixo, você só precisa posicionar.
        </p>
        <p className="lu-hint">
          Geralmente a imagem enviada é só a logo, não no tamanho final do vídeo (9:16 ou 16:9),
          por isso existe o editor de posição abaixo: ele gera a imagem final no tamanho certo,
          com a logo posicionada onde você escolher.
        </p>
        <div className="lu-field">
          <label className="lu-label">Imagem-fonte</label>
          <p className="lu-hint">
            {sourceImageUrl ? 'Imagem enviada.' : 'Nenhuma imagem enviada ainda.'}
          </p>
          <div className="lu-watermark-source-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={pickSourceImage}
              disabled={pickingImage || removingImage}
            >
              {pickingImage ? 'Escolhendo...' : sourceImageUrl ? 'Substituir imagem...' : 'Escolher imagem...'}
            </button>
            {sourceImageUrl && (
              <button
                type="button"
                className="btn btn-danger"
                onClick={removeSourceImage}
                disabled={pickingImage || removingImage}
              >
                {removingImage ? 'Removendo...' : 'Remover'}
              </button>
            )}
          </div>
          {sourceImageUrl && (
            <div className="lu-watermark-source-preview">
              <img src={sourceImageUrl} alt="Logo enviada" className="lu-watermark-source-preview__image" />
            </div>
          )}
        </div>
      </div>

      <div className="lu-watermark-editors">
        <div className="lu-card">
          <h2 className="lu-section-title">Formato curto (9:16)</h2>
          <WatermarkFormatEditor
            label="Formato curto (9:16)"
            frameWidth={1080}
            frameHeight={1920}
            sourceImageUrl={sourceImageUrl}
            state={watermark.short}
            onStateChange={(next) => updateFormatState('short', next)}
            bakedPreviewUrl={bakedShort}
            onSave={(bytes) => saveFormat('short', bytes)}
            saving={savingFormat === 'short'}
            safeZone={SHORT_SAFE_ZONE}
          />
        </div>

        <div className="lu-card">
          <h2 className="lu-section-title">Formato longo (16:9)</h2>
          <WatermarkFormatEditor
            label="Formato longo (16:9)"
            frameWidth={1920}
            frameHeight={1080}
            sourceImageUrl={sourceImageUrl}
            state={watermark.long}
            onStateChange={(next) => updateFormatState('long', next)}
            bakedPreviewUrl={bakedLong}
            onSave={(bytes) => saveFormat('long', bytes)}
            saving={savingFormat === 'long'}
            safeZone={LONG_SAFE_ZONE}
          />
        </div>
      </div>

      <div className="lu-card">
        <h2 className="lu-section-title">Ativar marca d'água</h2>
        <div className="lu-field">
          <div className="lu-watermark-toggle-row">
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="watermark-enabled"
                checked={watermark.enabled}
                disabled={!bothBaked}
                onChange={() => setEnabled(true)}
              />
              Ligada
            </label>
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="watermark-enabled"
                checked={!watermark.enabled}
                onChange={() => setEnabled(false)}
              />
              Desligada
            </label>
          </div>
          {!bothBaked && (
            <p className="lu-hint">
              Configure e salve a posição nos dois formatos (curto e longo) antes de poder ligar.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
