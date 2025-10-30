# Sprint 1 Deliverables

## A. File-level change outline (one-liners per file)

- **Create** `frontend/src/components/chart-labels/ChartLabels.tsx` — Canvas label renderer + editor with keyboard shortcuts
- **Modify** `frontend/src/pages/MonitorPage.tsx` — Add context menu handlers and ChartLabels import
- **Modify** `frontend/src/components/nifty-monitor/UnderlyingChart.tsx` — Integrate ChartLabels component and context menu
- **Create** `backend/migrations/001_create_ml_labels.sql` — Create ml_labels and ml_label_samples tables
- **Modify** `backend/app/routes/labels.py` — Update for metadata-only model and add WS broadcaster
- **Create** `backend/app/routes/label_stream.py` — WebSocket endpoint for label subscriptions
- **Create** `frontend/src/services/labels.ts` — Label service with CRUD and WebSocket client
- **Modify** `backend/app/main.py` — Initialize labels_hub and mount label stream route
- **Create** `frontend/src/types/labels.ts` — TypeScript interfaces for labels

## B. SQL migration for ml_labels and indexes (exact SQL block)

```sql
-- Migration: 001_create_ml_labels.sql

-- Create ml_labels table (metadata-only)
CREATE TABLE IF NOT EXISTS ml_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    label_type VARCHAR(50) NOT NULL,
    metadata JSONB NOT NULL,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Required metadata fields validation
ALTER TABLE ml_labels ADD CONSTRAINT metadata_required_fields CHECK (
    metadata ? 'timeframe' AND 
    metadata ? 'nearest_candle_timestamp_utc' AND 
    metadata ? 'sample_offset_seconds'
);

-- Create ml_label_samples table for ML export references
CREATE TABLE IF NOT EXISTS ml_label_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label_id UUID NOT NULL REFERENCES ml_labels(id) ON DELETE CASCADE,
    sample_uri TEXT NOT NULL,
    sample_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_ml_labels_user_symbol ON ml_labels(user_id, symbol);
CREATE INDEX idx_ml_labels_timestamp ON ml_labels((metadata->>'nearest_candle_timestamp_utc'));
CREATE INDEX idx_ml_labels_timeframe ON ml_labels((metadata->>'timeframe'));
CREATE GIN INDEX idx_ml_labels_tags ON ml_labels USING GIN(tags);
CREATE GIN INDEX idx_ml_labels_metadata ON ml_labels USING GIN(metadata);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ml_labels_updated_at BEFORE UPDATE ON ml_labels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

## C. HTTP and WebSocket message shapes (concise JSON examples)

### HTTP API
```json
// POST /labels request
{
  "symbol": "NIFTY",
  "label_type": "bullish",
  "metadata": {
    "timeframe": "5m",
    "nearest_candle_timestamp_utc": "2025-10-30T09:15:00Z",
    "sample_offset_seconds": 0,
    "price": 19500.50
  },
  "tags": ["manual", "reversal"]
}

// POST /labels response (201)
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "success": true,
  "message": "Label created"
}

// GET /labels?symbol=NIFTY&from=1698652800&to=1698739200
{
  "labels": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "user_id": "user123",
      "symbol": "NIFTY",
      "label_type": "bullish",
      "metadata": {
        "timeframe": "5m",
        "nearest_candle_timestamp_utc": "2025-10-30T09:15:00Z",
        "sample_offset_seconds": 0,
        "price": 19500.50
      },
      "tags": ["manual", "reversal"],
      "created_at": "2025-10-30T09:15:30Z"
    }
  ]
}
```

### WebSocket Messages
```json
// Subscribe for labels
{
  "action": "subscribe",
  "channel": "labels",
  "symbol": "NIFTY",
  "timeframe": "5m"
}

// Label create delta
{
  "type": "label.create",
  "seq": 1001,
  "issuedAt": "2025-10-30T09:15:30Z",
  "payload": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "user_id": "user123",
    "symbol": "NIFTY",
    "label_type": "bullish",
    "metadata": {
      "timeframe": "5m",
      "nearest_candle_timestamp_utc": "2025-10-30T09:15:00Z",
      "sample_offset_seconds": 0
    }
  }
}

// Label update delta
{
  "type": "label.update",
  "seq": 1002,
  "issuedAt": "2025-10-30T09:16:00Z",
  "payload": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "patch": {
      "label_type": "neutral",
      "metadata": {
        "pinnedCursorState": {
          "timestamp": "2025-10-30T09:15:00Z",
          "replay_mode": true
        }
      }
    }
  }
}

// Label delete delta
{
  "type": "label.delete",
  "seq": 1003,
  "issuedAt": "2025-10-30T09:16:30Z",
  "payload": {
    "id": "123e4567-e89b-12d3-a456-426614174000"
  }
}
```

## D. TypeScript client interfaces (minimal code block)

```typescript
// frontend/src/types/labels.ts

export interface LabelMetadata {
  timeframe: string;
  nearest_candle_timestamp_utc: string;
  sample_offset_seconds: number;
  price?: number;
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
```

## E. ChartLabels component props contract and callbacks

```tsx
// ChartLabels component signature
interface ChartLabelsProps {
  chart: IChartApi;
  series: ISeriesApi<'Candlestick'>;
  symbol: string;
  timeframe: string;
  labels: Label[];
  onLabelCreate: (timestamp: number, labelType: Label['label_type']) => Promise<void>;
  onLabelUpdate: (labelId: string, updates: Partial<Label>) => Promise<void>;
  onLabelDelete: (labelId: string) => Promise<void>;
  onShowChart: (labelId: string) => void;
}

// Usage in UnderlyingChart
<ChartLabels
  chart={chartRef.current}
  series={seriesRef.current}
  symbol={symbol}
  timeframe={timeframe}
  labels={labels}
  onLabelCreate={handleLabelCreate}  // Creates label via API, shows optimistic update
  onLabelUpdate={handleLabelUpdate}  // Updates label metadata, handles pinned state
  onLabelDelete={handleLabelDelete}  // Removes label, updates UI optimistically
  onShowChart={handleShowChart}      // Opens Show Chart popup for label
/>
```

### Callback behaviors:
- **onLabelCreate**: Posts to API, optimistically adds marker, reconciles on response
- **onLabelUpdate**: Patches label metadata, broadcasts WS update, handles pin state
- **onLabelDelete**: Removes from backend, optimistically removes marker
- **onShowChart**: Triggers parent to open Show Chart popup with label context

### Keyboard shortcuts:
- **L**: Open label editor at crosshair position
- **Esc**: Cancel label editor or context menu

### Optimistic UI:
- Label markers appear immediately on create
- Updates/deletes reflect instantly
- Reconcile with server response, rollback on error

## F. Minimal server-side API handler pseudocode

```python
# backend/app/routes/labels.py

@router.post("/labels", status_code=201)
async def create_label(
    label_data: LabelCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncConnection = Depends(get_db),
    labels_hub: RealTimeHub = Depends(get_labels_hub)
):
    # Permission check
    if not current_user.can_create_labels:
        raise HTTPException(403, "Insufficient permissions")
    
    # Validate metadata content
    required_fields = ["timeframe", "nearest_candle_timestamp_utc", "sample_offset_seconds"]
    if not all(field in label_data.metadata for field in required_fields):
        raise HTTPException(400, "Missing required metadata fields")
    
    # Insert metadata-only record
    label_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO ml_labels (id, user_id, symbol, label_type, metadata, tags)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        label_id, current_user.id, label_data.symbol, 
        label_data.label_type, json.dumps(label_data.metadata), label_data.tags
    )
    
    # Broadcast WS delta (no series data)
    await labels_hub.broadcast({
        "type": "label.create",
        "seq": get_next_seq(),
        "issuedAt": datetime.utcnow().isoformat(),
        "payload": {
            "id": label_id,
            "user_id": current_user.id,
            "symbol": label_data.symbol,
            "label_type": label_data.label_type,
            "metadata": label_data.metadata
        }
    })
    
    return {"id": label_id, "success": True, "message": "Label created"}
```

## G. Three test cases with explicit assertions

### 1. Label create persists metadata and WS broadcast
```python
async def test_label_create_and_broadcast():
    # Setup WS subscriber
    ws_messages = []
    await subscribe_to_labels("NIFTY", "5m", ws_messages.append)
    
    # Create label via API
    response = await client.post("/labels", json={
        "symbol": "NIFTY",
        "label_type": "bullish",
        "metadata": {
            "timeframe": "5m",
            "nearest_candle_timestamp_utc": "2025-10-30T09:15:00Z",
            "sample_offset_seconds": 0
        }
    })
    
    # Assert API response
    assert response.status_code == 201
    assert response.json()["success"] == True
    label_id = response.json()["id"]
    
    # Assert DB contains metadata
    label = await db.fetchrow("SELECT * FROM ml_labels WHERE id = $1", label_id)
    assert label["metadata"]["timeframe"] == "5m"
    assert label["metadata"]["nearest_candle_timestamp_utc"] == "2025-10-30T09:15:00Z"
    
    # Assert WS broadcast received within 1s
    await asyncio.sleep(0.1)
    assert len(ws_messages) == 1
    assert ws_messages[0]["type"] == "label.create"
    assert ws_messages[0]["payload"]["id"] == label_id
```

### 2. Label update patches metadata
```python
async def test_label_update_patches_metadata():
    # Create label first
    label_id = await create_test_label()
    
    # Update with pinned cursor state
    response = await client.patch(f"/labels/{label_id}", json={
        "metadata": {
            "pinnedCursorState": {
                "timestamp": "2025-10-30T09:20:00Z",
                "replay_mode": True
            }
        }
    })
    
    # Assert response
    assert response.status_code == 200
    
    # Assert metadata merged (not replaced)
    label = await db.fetchrow("SELECT * FROM ml_labels WHERE id = $1", label_id)
    assert label["metadata"]["timeframe"] == "5m"  # Original preserved
    assert label["metadata"]["pinnedCursorState"]["replay_mode"] == True  # New added
    
    # Assert WS broadcast
    ws_msg = await get_latest_ws_message()
    assert ws_msg["type"] == "label.update"
    assert ws_msg["payload"]["patch"]["metadata"]["pinnedCursorState"] is not None
```

### 3. UI ChartLabels optimistic updates
```typescript
// Frontend test
it('should show optimistic label and reconcile with server', async () => {
  // Mock API to delay response
  mockCreateLabel.mockImplementation(() => 
    new Promise(resolve => setTimeout(() => resolve({ id: 'server-id' }), 500))
  );
  
  // Render chart with labels
  const { getByTestId } = render(
    <ChartLabels 
      labels={[]} 
      onLabelCreate={mockCreateLabel}
    />
  );
  
  // Trigger label creation
  fireEvent.contextMenu(getByTestId('chart-canvas'));
  fireEvent.click(getByText('Set Bullish'));
  
  // Assert optimistic marker appears immediately
  expect(getByTestId('label-marker-optimistic')).toBeInTheDocument();
  
  // Wait for server response
  await waitFor(() => {
    expect(mockCreateLabel).toHaveBeenCalledWith(
      expect.any(Number), // timestamp
      'bullish'
    );
  });
  
  // Assert reconciled with server ID
  expect(queryByTestId('label-marker-optimistic')).not.toBeInTheDocument();
  expect(getByTestId('label-marker-server-id')).toBeInTheDocument();
});
```

## H. Sprint 1 acceptance checklist

- [ ] Right-click on chart opens context menu with label options
- [ ] Context menu anchors to nearest candle timestamp
- [ ] POST /labels returns 201 with label ID
- [ ] ml_labels rows contain required metadata keys: timeframe, nearest_candle_timestamp_utc, sample_offset_seconds
- [ ] ml_labels rows do NOT contain OHLC data or timeframe snapshots
- [ ] WS label.create broadcast received by subscribed clients within 1s
- [ ] Labels persist and reload on page refresh
- [ ] Keyboard shortcut 'L' opens label editor
- [ ] Escape key closes label editor/context menu
- [ ] Label markers render at correct chart positions
- [ ] Optimistic updates show immediately on create/update/delete
- [ ] Server errors roll back optimistic changes

## I. Short demo script

```bash
# 1. Start backend with label endpoints
cd backend
python -m app.main

# 2. Subscribe to label WebSocket
wscat -c ws://localhost:8081/labels/stream
> {"action":"subscribe","channel":"labels","symbol":"NIFTY","timeframe":"5m"}

# 3. Create a label via API
curl -X POST http://localhost:8081/api/labels \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "NIFTY",
    "label_type": "bullish",
    "metadata": {
      "timeframe": "5m",
      "nearest_candle_timestamp_utc": "2025-10-30T09:15:00Z",
      "sample_offset_seconds": 0,
      "price": 19500.50
    },
    "tags": ["demo", "test"]
  }'

# 4. Verify WebSocket receives broadcast
# Expected: {"type":"label.create","seq":1,"payload":{...}}

# 5. Open frontend and right-click chart
# Expected: Context menu appears with label options
# Click "Set Bullish" to create label via UI
```

## Implementation Notes

- DO NOT store OHLC/timeframe snapshots in ml_labels
- Use metadata pointers only (timeframe, timestamp, offset)
- Client fetches series on-demand via /historical/series
- Respect limits: strikes ±20 default, configurable pinned popups
- Use optimistic UI with server reconciliation
- WS deltas must be compact with seq numbers and heartbeats