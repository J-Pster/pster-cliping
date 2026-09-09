import { useState } from 'react'
import { NavLink } from 'react-router-dom'

interface NavItem {
  to: string
  label: string
  glyph: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/new-clip', label: 'New Clip', glyph: '✂' },
  { to: '/rebrand', label: 'Rebrand', glyph: '↻' },
  { to: '/marca-dagua', label: "Marca d'água", glyph: '🖼' },
  { to: '/propaganda-eleitoral', label: 'Propaganda eleitoral', glyph: '📢' },
  { to: '/knowledge-base', label: 'Base de conhecimento', glyph: '▤' },
  { to: '/settings', label: 'Settings', glyph: '⚙' }
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
              {item.glyph}
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
            {expanded ? '←' : '→'}
          </span>
          {expanded && <span className="lu-sidebar__label">Recolher</span>}
        </button>
      </div>
    </aside>
  )
}
