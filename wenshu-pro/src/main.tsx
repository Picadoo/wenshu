import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import CssBaseline from '@mui/material/CssBaseline';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { App } from './app';
import './styles.css';

const theme = createTheme({
  palette: { primary: { main: '#5b43b6' }, background: { default: '#f5f6fa', paper: '#fff' } },
  typography: { fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif' },
  shape: { borderRadius: 10 },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ThemeProvider theme={theme}><CssBaseline /><BrowserRouter><App /></BrowserRouter></ThemeProvider></React.StrictMode>
);
