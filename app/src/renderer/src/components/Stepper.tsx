export interface StepDef {
  id: string
  label: string
}

/** Indicador de passos tipo aba sublinhada. So deixa clicar em passos ja
 * visitados (indice <= furthestIndex): avancar so pelo botao "Proximo", que
 * valida o passo atual antes de liberar o seguinte. */
export default function Stepper({
  steps,
  current,
  furthestIndex,
  onSelect
}: {
  steps: StepDef[]
  current: string
  furthestIndex: number
  onSelect: (id: string) => void
}): React.JSX.Element {
  return (
    <div className="lu-steps" role="tablist">
      {steps.map((step, index) => {
        const reachable = index <= furthestIndex
        return (
          <button
            key={step.id}
            type="button"
            role="tab"
            aria-selected={step.id === current}
            disabled={!reachable}
            className={`lu-steps__item${step.id === current ? ' lu-steps__item--active' : ''}`}
            onClick={() => reachable && onSelect(step.id)}
          >
            <span className="lu-steps__number">{index + 1}</span>
            <span className="lu-steps__label">{step.label}</span>
          </button>
        )
      })}
    </div>
  )
}
