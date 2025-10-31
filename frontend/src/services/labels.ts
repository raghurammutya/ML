import { api } from './api';
import type { 
  Label, 
  LabelCreateRequest, 
  LabelUpdateRequest, 
  LabelResponse,
  LabelDeltaWSPayload,
  LabelSubscribeMessage 
} from '../types/labels';

// CRUD operations
export const createLabel = async (label: LabelCreateRequest): Promise<LabelResponse> => {
  const response = await api.post<LabelResponse>('/api/labels', label);
  return response.data;
};

export const updateLabel = async (labelId: string, updates: LabelUpdateRequest): Promise<LabelResponse> => {
  const response = await api.patch<LabelResponse>(`/api/labels/${labelId}`, updates);
  return response.data;
};

export const deleteLabel = async (labelId: string, symbol: string, timeframe: string, timestamp: number): Promise<LabelResponse> => {
  const response = await api.delete<LabelResponse>('/api/labels', { 
    data: { 
      id: labelId,
      symbol, 
      timeframe, 
      timestamp 
    } 
  });
  return response.data;
};

export const fetchLabels = async (
  symbol: string, 
  timeframe: string, 
  from?: number, 
  to?: number
): Promise<{ labels: Label[] }> => {
  const response = await api.get<{ labels: Label[] }>('/api/labels', {
    params: { symbol, timeframe, from, to }
  });
  return response.data;
};

// WebSocket connection builder
const buildLabelsWsUrl = (): string => {
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api';
  const base = API_BASE_URL;
  
  // Check if the base URL is absolute
  const isAbsolute = base.startsWith('http://') || base.startsWith('https://');
  
  let wsUrl: string;
  if (isAbsolute) {
    // Replace http/https with ws/wss
    const protocol = base.startsWith('https://') ? 'wss:' : 'ws:';
    wsUrl = base.replace(/^https?:/, protocol);
  } else {
    // Relative URL - construct based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    wsUrl = `${protocol}//${host}${base}`;
  }
  
  // Add the labels stream endpoint
  return `${wsUrl}/labels/stream`;
};

// WebSocket connection for real-time labels
export const connectLabelStream = (): WebSocket => {
  const wsUrl = buildLabelsWsUrl();
  return new WebSocket(wsUrl);
};

// Helper to subscribe to labels for a specific symbol/timeframe
export const subscribeLabelStream = (
  ws: WebSocket, 
  symbol: string, 
  timeframe: string
): void => {
  if (ws.readyState === WebSocket.OPEN) {
    const message: LabelSubscribeMessage = {
      action: 'subscribe',
      channel: 'labels',
      symbol,
      timeframe
    };
    ws.send(JSON.stringify(message));
  }
};

// Helper to parse WebSocket messages
export const parseLabelMessage = (data: string): LabelDeltaWSPayload | null => {
  try {
    const message = JSON.parse(data);
    if (message.type && message.type.startsWith('label.')) {
      return message as LabelDeltaWSPayload;
    }
    return null;
  } catch (error) {
    console.error('Failed to parse label message:', error);
    return null;
  }
};

// Helper to convert timestamp to UTC ISO string
export const timestampToUTC = (timestamp: number): string => {
  return new Date(timestamp * 1000).toISOString();
};

// Helper to convert UTC ISO string to timestamp
export const utcToTimestamp = (utc: string): number => {
  return new Date(utc).getTime() / 1000;
};

// Popup subscription helpers
export interface PopupSubscribeMessage {
  action: 'subscribe_popup'
  underlying: string
  strike: number
  expiry: string
  timeframe: string
}

export interface PopupUpdateMessage {
  type: 'popup_update'
  seq: number
  timestamp: string
  candle: {
    o: number
    h: number
    l: number
    c: number
    v: number
  }
  metrics: {
    iv: number
    delta: number
    gamma: number
    theta: number
    vega: number
    premium: number
    oi: number
    oi_delta: number
  }
}

// Create popup WebSocket subscription
export const subscribePopup = (
  ws: WebSocket,
  underlying: string,
  strike: number,
  expiry: string,
  timeframe: string = '1m'
): void => {
  if (ws.readyState === WebSocket.OPEN) {
    const message: PopupSubscribeMessage = {
      action: 'subscribe_popup',
      underlying,
      strike,
      expiry,
      timeframe
    };
    ws.send(JSON.stringify(message));
  }
};

// Parse popup update messages
export const parsePopupMessage = (data: string): PopupUpdateMessage | null => {
  try {
    const message = JSON.parse(data);
    if (message.type === 'popup_update') {
      return message as PopupUpdateMessage;
    }
    return null;
  } catch (error) {
    console.error('Failed to parse popup message:', error);
    return null;
  }
};