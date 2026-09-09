import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import SettingsRoute from './routes/Settings'
import NewClipRoute from './routes/NewClip'
import RebrandRoute from './routes/Rebrand'
import KnowledgeBaseRoute from './routes/KnowledgeBase'
import WatermarkRoute from './routes/Watermark'
import EleitoralRoute from './routes/Eleitoral'

export default function App(): React.JSX.Element {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/new-clip" replace />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="/new-clip" element={<NewClipRoute />} />
        <Route path="/rebrand" element={<RebrandRoute />} />
        <Route path="/marca-dagua" element={<WatermarkRoute />} />
        <Route path="/propaganda-eleitoral" element={<EleitoralRoute />} />
        <Route path="/knowledge-base" element={<KnowledgeBaseRoute />} />
        <Route path="*" element={<Navigate to="/new-clip" replace />} />
      </Route>
    </Routes>
  )
}
