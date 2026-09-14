import { useState } from 'react'
import { ChevronDown, type LucideIcon } from 'lucide-react'

interface DisclosureProps {
  title: string
  subtitle?: string
  icon?: LucideIcon
  badge?: string
  defaultOpen?: boolean
  children: React.ReactNode
}

/** Secao colapsavel reutilizada em toda a tela de Settings (chaves extras,
 * publicacao automatica, avancado): caixa propria com radius/borda, nao uma
 * regra horizontal cortando o card por cima como antes. */
export default function Disclosure({
  title,
  subtitle,
  icon: Icon,
  badge,
  defaultOpen = false,
  children
}: DisclosureProps): React.JSX.Element {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`lu-disclosure${open ? ' lu-disclosure--open' : ''}`}>
      <button
        type="button"
        className="lu-disclosure__trigger"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        {Icon && (
          <span className="lu-disclosure__icon" aria-hidden="true">
            <Icon size={16} strokeWidth={2} />
          </span>
        )}
        <span className="lu-disclosure__text">
          <span className="lu-disclosure__title">{title}</span>
          {subtitle && <span className="lu-disclosure__subtitle">{subtitle}</span>}
        </span>
        {badge && <span className="lu-disclosure__badge">{badge}</span>}
        <span className="lu-disclosure__chevron" aria-hidden="true">
          <ChevronDown size={16} strokeWidth={2} />
        </span>
      </button>
      {open && <div className="lu-disclosure__body">{children}</div>}
    </div>
  )
}
