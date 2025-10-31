// frontend/src/types/labels.ts

export interface LabelMetadata {
  timeframe: string;
  nearest_candle_timestamp_utc: string;
  sample_offset_seconds: number;
  price?: number;
  strike?: number;
  bucket?: string;
  pinnedCursorState?: {
    timestamp: string;
    replay_mode: boolean;
  };
}

export interface Label {
  id: string;
  user_id: string;
  symbol: string;
  label_type: 'bullish' | 'bearish' | 'neutral' | 'exit_bullish' | 'exit_bearish';
  metadata: LabelMetadata;
  tags: string[];
  created_at: string;
  updated_at?: string;
}

export interface LabelCreateRequest {
  symbol: string;
  label_type: Label['label_type'];
  metadata: LabelMetadata;
  tags?: string[];
}

export interface LabelUpdateRequest {
  metadata?: Partial<LabelMetadata>;
  label_type?: Label['label_type'];
  tags?: string[];
}

export interface LabelDeltaWSPayload {
  type: 'label.create' | 'label.update' | 'label.delete';
  seq: number;
  issuedAt: string;
  payload: {
    id: string;
    user_id?: string;
    symbol?: string;
    label_type?: Label['label_type'];
    metadata?: Partial<LabelMetadata>;
    patch?: Partial<Label>;
  };
}

export interface LabelSubscribeMessage {
  action: 'subscribe';
  channel: 'labels';
  symbol: string;
  timeframe: string;
}

export interface LabelResponse {
  id?: string;
  success: boolean;
  message: string;
}