import { Outlet } from 'react-router-dom'
import Header from './Header'
import Sidebar from './Sidebar'
import ErrorBoundary from './ErrorBoundary'
import UpdateBanner from './UpdateBanner'

export default function Layout(): React.JSX.Element {
  return (
    <div className="lu-shell">
      <Header />
      <UpdateBanner />
      <div className="lu-shell__body">
        <Sidebar />
        <main className="lu-content">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
