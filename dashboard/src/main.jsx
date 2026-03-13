import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from 'sonner';
import App from './App';
import './styles/globals.css';
// Register all built-in GenUI components (chart, table, code, etc.)
import './lib/genui-builtins';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    <Toaster richColors position="bottom-right" />
  </StrictMode>,
);
