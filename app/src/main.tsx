import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, HashRouter } from 'react-router';
import CssBaseline from '@mui/material/CssBaseline';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { App } from './app';
import { APP_BASE, IS_PAGES_PREVIEW } from './lib/app-env';
import './styles.css';

const theme = createTheme({
  palette: { primary: { main: '#5b43b6' }, background: { default: '#f5f6fa', paper: '#fff' } },
  typography: { fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif' },
  shape: { borderRadius: 10 },
});

const app = IS_PAGES_PREVIEW ? <HashRouter><App /></HashRouter> : <BrowserRouter basename={APP_BASE}><App /></BrowserRouter>;
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ThemeProvider theme={theme}><CssBaseline />{app}</ThemeProvider></React.StrictMode>
);
