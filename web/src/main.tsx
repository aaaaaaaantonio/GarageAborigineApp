import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { telegram } from './telegram/webapp';
import './theme.css';

telegram.init();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
