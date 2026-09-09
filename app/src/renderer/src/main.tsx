import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App'

import '@fontsource/poppins/400.css'
import '@fontsource/poppins/500.css'
import '@fontsource/poppins/600.css'
import '@fontsource/poppins/700.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/buttons.css'
import './styles/forms.css'
import './styles/layout.css'
import './styles/screens.css'
import './styles/watermark-editor.css'

const container = document.getElementById('root')
if (!container) {
  throw new Error('Elemento #root nao encontrado em index.html')
}

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>
)
