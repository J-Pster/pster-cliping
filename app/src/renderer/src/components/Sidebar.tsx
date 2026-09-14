import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Image,
  Megaphone,
  RefreshCw,
  Scissors,
  Settings,
  type LucideIcon
} from 'lucide-react'

interface NavItem {
  to: string
  label: string
  Icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { to: '/new-clip', label: 'Novo clipe', Icon: Scissors },
  { to: '/rebrand', label: 'Rebranding', Icon: RefreshCw },
  { to: '/marca-dagua', label: "Marca d'água", Icon: Image },
  { to: '/propaganda-eleitoral', label: 'Eleitoral', Icon: Megaphone },
  { to: '/knowledge-base', label: 'Base de conhecimento', Icon: BookOpen },
  { to: '/settings', label: 'Configuracoes', Icon: Settings }
]

export default function Sidebar(): React.JSX.Element {
  const [expanded, setExpanded] = useState(true)

  return (
    <aside className={`lu-sidebar${expanded ? ' lu-sidebar--expanded' : ''}`}>
      <nav className="lu-sidebar__nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `lu-sidebar__btn${isActive ? ' lu-sidebar__btn--active' : ''}`
            }
            title={item.label}
          >
            <span className="lu-sidebar__glyph" aria-hidden="true">
              <item.Icon size={18} strokeWidth={2} />
            </span>
            {expanded && <span className="lu-sidebar__label">{item.label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="lu-sidebar__footer">
        <button
          type="button"
          className="lu-sidebar__btn"
          onClick={() => setExpanded((value) => !value)}
          title={expanded ? 'Recolher menu' : 'Expandir menu'}
        >
          <span className="lu-sidebar__glyph" aria-hidden="true">
            {expanded ? <ChevronLeft size={18} strokeWidth={2} /> : <ChevronRight size={18} strokeWidth={2} />}
          </span>
          {expanded && <span className="lu-sidebar__label">Recolher</span>}
        </button>
      </div>
    </aside>
  )
}
