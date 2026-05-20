import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

console.log('[main] main.tsx executing')
ReactDOM.createRoot(document.getElementById('root')!).render(
  <App />
)
