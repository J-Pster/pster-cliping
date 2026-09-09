export default function Header(): React.JSX.Element {
  return (
    <header className="lu-header">
      <div className="lu-header__brand">
        <span className="lu-header__name">Pster Clipping</span>
      </div>
      <div className="lu-header__meta">
        <span className="lu-header__author">Joao P. V. Freitas</span>
        <span className="lu-header__version">v{__APP_VERSION__}</span>
      </div>
    </header>
  )
}
