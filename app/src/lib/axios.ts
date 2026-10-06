import axios from 'axios';
import { loadServerConfig } from './runtime-config';

const client = axios.create({ withCredentials: true });
client.interceptors.request.use((config) => {
  config.baseURL = loadServerConfig().baseUrl;
  return config;
});
export default client;
