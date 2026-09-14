import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Header from './Header'
import Sidebar from './Sidebar'
import ErrorBoundary from './ErrorBoundary'
import UpdateBanner from './UpdateBanner'

export default function Layout(): React.JSX.Element {
  const [updateBarVisible, setUpdateBarVisible] = useState(false)

  return (
    <div className="lu-shell">
      <Header />
      <div className="lu-shell__body">
        <Sidebar />
        <main className={`lu-content${updateBarVisible ? ' lu-content--with-update-bar' : ''}`}>
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <UpdateBanner onVisibleChange={setUpdateBarVisible} />
    </div>
  )
}
