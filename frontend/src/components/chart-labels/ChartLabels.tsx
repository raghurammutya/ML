import React, { useEffect, useRef, useState, useCallback } from 'react';
import { IChartApi, ISeriesApi, SeriesMarker, Time } from 'lightweight-charts';
import { createPortal } from 'react-dom';
import { Label } from '../../types/labels';

export type ChartContextMenuAction =
  | {
      kind: 'copy'
      timestamp: number | null
      price: number | null
    }
  | {
      kind: 'alerts'
      timestamp: number | null
      price: number | null
    }
  | {
      kind: 'show-chart'
      variant: 'call-strike' | 'put-strike' | 'straddle-strike'
      timestamp: number | null
      price: number | null
    }

interface ChartLabelsProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  symbol: string;
  timeframe: string;
  labels: Label[];
  onLabelCreate: (timestamp: number, labelType: Label['label_type']) => Promise<void>;
  onLabelUpdate: (labelId: string, updates: Partial<Label>) => Promise<void>;
  onLabelDelete: (labelId: string) => Promise<void>;
  onShowChart: (labelId: string) => void;
  onContextAction?: (action: ChartContextMenuAction) => void;
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  timestamp: number | null;
  price: number | null;
  existingLabel?: Label;
}

interface LabelEditorState {
  visible: boolean;
  x: number;
  y: number;
  timestamp: number;
  labelType?: Label['label_type'];
  existingLabel?: Label;
}

const LABEL_COLORS = {
  bullish: '#00CC88',
  bearish: '#FF3366',
  neutral: '#FFD700',
  exit_bullish: '#00FF88',
  exit_bearish: '#FF6666'
};

const LABEL_SHAPES = {
  bullish: 'arrowUp' as const,
  bearish: 'arrowDown' as const,
  neutral: 'circle' as const,
  exit_bullish: 'arrowUp' as const,
  exit_bearish: 'arrowDown' as const
};

const LABEL_POSITIONS = {
  bullish: 'belowBar' as const,
  bearish: 'aboveBar' as const,
  neutral: 'inBar' as const,
  exit_bullish: 'belowBar' as const,
  exit_bearish: 'aboveBar' as const
};

const LABEL_MENU_OPTIONS: Array<{ type: Label['label_type']; label: string }> = [
  { type: 'bullish', label: 'Set Bullish' },
  { type: 'bearish', label: 'Set Bearish' },
  { type: 'neutral', label: 'Set Neutral' },
  { type: 'exit_bullish', label: 'Exit Bullish' },
  { type: 'exit_bearish', label: 'Exit Bearish' },
];

export const ChartLabels: React.FC<ChartLabelsProps> = ({
  chart,
  series,
  symbol,
  timeframe,
  labels,
  onLabelCreate,
  onLabelDelete,
  onShowChart,
  onContextAction,
}) => {
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    timestamp: null,
    price: null,
  });

  const [labelEditor, setLabelEditor] = useState<LabelEditorState>({
    visible: false,
    x: 0,
    y: 0,
    timestamp: 0
  });

  const [openSubmenu, setOpenSubmenu] = useState<{ type: 'showChart' | 'label'; x: number; y: number } | null>(null);

  const resetContextMenu = useCallback(() => {
    setContextMenu({ visible: false, x: 0, y: 0, timestamp: null, price: null })
    setOpenSubmenu(null)
  }, [])
  const [optimisticLabels, setOptimisticLabels] = useState<Label[]>([]);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const submenuRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);

  // Convert labels to chart markers
  const createMarkers = useCallback((labelsToConvert: Label[]): SeriesMarker<Time>[] => {
    return labelsToConvert.map(label => {
      const timestamp = new Date(label.metadata.nearest_candle_timestamp_utc).getTime() / 1000;
      return {
        time: timestamp as Time,
        position: LABEL_POSITIONS[label.label_type],
        color: LABEL_COLORS[label.label_type],
        shape: LABEL_SHAPES[label.label_type],
        text: label.label_type.replace('_', ' ').toUpperCase(),
        id: label.id,
        size: 2
      };
    });
  }, []);

  // Update markers when labels change
  useEffect(() => {
    if (!series || !Array.isArray(labels)) return;
    
    const allLabels = [...(labels || []), ...(optimisticLabels || [])];
    const markers = createMarkers(allLabels);
    series.setMarkers(markers);
  }, [series, labels, optimisticLabels, createMarkers]);

  // Handle right-click on chart
  useEffect(() => {
    if (!chart) return;

    const handleContextMenu = (event: MouseEvent) => {
      event.preventDefault();
      
      if (!series) return;
      
      // Use timeScale coordinateToTime instead of coordinateToLogical
      const timeValue = chart.timeScale().coordinateToTime(event.offsetX);
      if (!timeValue) return;

      const timestamp = typeof timeValue === 'number' 
        ? timeValue 
        : typeof timeValue === 'string' 
          ? new Date(timeValue).getTime() / 1000
          : new Date(timeValue.year, timeValue.month - 1, timeValue.day).getTime() / 1000;
      const priceValue = series.coordinateToPrice(event.offsetY);
      
      // Check if label exists at this timestamp
      const existingLabel = labels.find(l => {
        const labelTime = new Date(l.metadata.nearest_candle_timestamp_utc).getTime() / 1000;
        return Math.abs(labelTime - timestamp) < 60; // Within 1 minute
      });

      setOpenSubmenu(null);
      setContextMenu({
        visible: true,
        x: event.clientX,
        y: event.clientY,
        timestamp,
        price: typeof priceValue === 'number' && Number.isFinite(priceValue) ? priceValue : null,
        existingLabel
      });
    };

    const container = chart.chartElement();
    container.addEventListener('contextmenu', handleContextMenu);

    return () => {
      container.removeEventListener('contextmenu', handleContextMenu);
    };
  }, [chart, series, labels]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'l' || event.key === 'L') {
        if (!chart || !series) return;
        
        // For keyboard shortcut, use center of chart
        const chartWidth = chart.timeScale().width();
        const centerX = chartWidth / 2;
        
        const timeValue = chart.timeScale().coordinateToTime(centerX);
        if (!timeValue) return;

        const timestamp = typeof timeValue === 'number' 
        ? timeValue 
        : typeof timeValue === 'string' 
          ? new Date(timeValue).getTime() / 1000
          : new Date(timeValue.year, timeValue.month - 1, timeValue.day).getTime() / 1000;

        setLabelEditor({
          visible: true,
          x: centerX,
          y: 100, // Fixed position from top
          timestamp
        });
      } else if (event.key === 'Escape') {
        resetContextMenu();
        setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [chart, series, resetContextMenu]);

  // Close context menu on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const targetNode = event.target as Node
      const insideMenu = contextMenuRef.current?.contains(targetNode)
      const insideSubmenu = submenuRef.current?.contains(targetNode)
      if (!insideMenu && !insideSubmenu) {
        resetContextMenu()
      }
      if (editorRef.current && !editorRef.current.contains(event.target as Node)) {
        setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
      }
    };

    if (contextMenu.visible || labelEditor.visible) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [contextMenu.visible, labelEditor.visible, resetContextMenu]);

  const handleLabelCreate = async (labelType: Label['label_type']) => {
    if (!contextMenu.timestamp) return;

    const timestampSeconds = contextMenu.timestamp;
    const timestamp = new Date(timestampSeconds * 1000).toISOString();
    const optimisticId = `optimistic-${Date.now()}`;
    
    // Add optimistic label
    const optimisticLabel: Label = {
      id: optimisticId,
      user_id: 'current-user', // Will be set by backend
      symbol,
      label_type: labelType,
      metadata: {
        timeframe,
        nearest_candle_timestamp_utc: timestamp,
        sample_offset_seconds: 0
      },
      tags: ['manual'],
      created_at: new Date().toISOString()
    };

    setOptimisticLabels(prev => [...prev, optimisticLabel]);
    resetContextMenu();

    try {
      await onLabelCreate(timestampSeconds, labelType);
      // Remove optimistic label after successful creation
      setOptimisticLabels(prev => prev.filter(l => l.id !== optimisticId));
    } catch (error) {
      // Remove optimistic label on error
      setOptimisticLabels(prev => prev.filter(l => l.id !== optimisticId));
      console.error('Failed to create label:', error);
    }
  };

  const handleLabelDelete = async (labelId: string) => {
    resetContextMenu();
    
    try {
      await onLabelDelete(labelId);
    } catch (error) {
      console.error('Failed to delete label:', error);
    }
  };

  const handleShowChart = (labelId: string) => {
    resetContextMenu();
    onShowChart(labelId);
  };

  const formatTimestampDisplay = (timestamp: number | null): string => {
    if (!timestamp) return 'n/a'
    const date = new Date(timestamp * 1000)
    return date.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: true,
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const handleCopy = async () => {
    const timestamp = contextMenu.timestamp
    const price = contextMenu.price
    const formattedTime = formatTimestampDisplay(timestamp)
    const priceText = price != null ? price.toFixed(2) : '—'
    const payload = `${symbol} (${timeframe}) • ${formattedTime}${price != null ? ` • ₹${priceText}` : ''}`

    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(payload)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = payload
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
      }
    } catch (error) {
      console.error('Failed to copy context payload', error)
    }

    onContextAction?.({
      kind: 'copy',
      timestamp: timestamp ?? null,
      price: price ?? null,
    })
    resetContextMenu()
  }

  const handleAlertsAction = () => {
    onContextAction?.({
      kind: 'alerts',
      timestamp: contextMenu.timestamp ?? null,
      price: contextMenu.price ?? null,
    })
    resetContextMenu()
  }

  const handleShowChartVariant = (variant: 'call-strike' | 'put-strike' | 'straddle-strike') => {
    onContextAction?.({
      kind: 'show-chart',
      variant,
      timestamp: contextMenu.timestamp ?? null,
      price: contextMenu.price ?? null,
    })
    resetContextMenu()
  }

  const toggleSubmenu = (type: 'showChart' | 'label', event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const rect = event.currentTarget.getBoundingClientRect()
    const x = Math.min(rect.right + 6, window.innerWidth - 220)
    const y = Math.min(rect.top, window.innerHeight - 220)
    setOpenSubmenu((prev) => {
      if (prev && prev.type === type) {
        return null
      }
      return { type, x, y }
    })
  }

  const hoverHandlers = (isActive = false) => ({
    onMouseEnter: (event: React.MouseEvent<HTMLButtonElement>) => {
      if (!isActive) {
        event.currentTarget.style.backgroundColor = '#f3f4f6'
      }
    },
    onMouseLeave: (event: React.MouseEvent<HTMLButtonElement>) => {
      if (!isActive) {
        event.currentTarget.style.backgroundColor = 'transparent'
      }
    },
  })

  const menuLeft = Math.min(contextMenu.x, window.innerWidth - 220)
  const menuTop = Math.min(contextMenu.y, window.innerHeight - 260)
  const formattedTime = formatTimestampDisplay(contextMenu.timestamp)
  const formattedPrice = contextMenu.price != null ? contextMenu.price.toFixed(2) : '—'
  const currentLabelType = contextMenu.existingLabel?.label_type
  const mainMenuStyle: React.CSSProperties = {
    position: 'fixed',
    left: `${menuLeft}px`,
    top: `${menuTop}px`,
    background: '#ffffff',
    color: '#1f2937',
    border: '1px solid rgba(15, 23, 42, 0.12)',
    borderRadius: 10,
    boxShadow: '0 12px 32px rgba(15, 23, 42, 0.18)',
    zIndex: 2147483647,
    padding: '8px',
    minWidth: '210px',
    fontSize: '14px',
    pointerEvents: 'auto',
    userSelect: 'none',
  }
  const submenuStyle: React.CSSProperties = {
    position: 'fixed',
    left: `${Math.min(openSubmenu ? openSubmenu.x : menuLeft + 200, window.innerWidth - 220)}px`,
    top: `${Math.min(openSubmenu ? openSubmenu.y : menuTop, window.innerHeight - 260)}px`,
    background: '#ffffff',
    color: '#1f2937',
    border: '1px solid rgba(15, 23, 42, 0.12)',
    borderRadius: 10,
    boxShadow: '0 12px 28px rgba(15, 23, 42, 0.18)',
    zIndex: 2147483648,
    padding: '8px',
    minWidth: '210px',
    fontSize: '14px',
    pointerEvents: 'auto',
    userSelect: 'none',
  }
  const baseMenuButtonStyle: React.CSSProperties = {
    padding: '8px 12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    borderRadius: 6,
    color: '#1f2937',
    fontSize: '14px',
    width: '100%',
    textAlign: 'left',
  }
  const separatorStyle: React.CSSProperties = {
    height: '1px',
    background: '#e5e7eb',
    margin: '6px 0',
  }

  return (
    <>
      {/* Context Menu */}
      {contextMenu.visible && (
        <>
          {createPortal(
            <div
              ref={contextMenuRef}
              style={mainMenuStyle}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
              onContextMenu={(e) => {
                e.preventDefault()
                e.stopPropagation()
              }}
            >
              <button
                type="button"
                style={{ ...baseMenuButtonStyle }}
                onClick={handleCopy}
                {...hoverHandlers()}
              >
                <span>Copy price / time</span>
              </button>

              <div style={separatorStyle} />

              <button
                type="button"
                style={{
                  ...baseMenuButtonStyle,
                  fontWeight: openSubmenu?.type === 'showChart' ? 600 : 500,
                  background: openSubmenu?.type === 'showChart' ? '#f3f4f6' : 'transparent',
                }}
                onClick={(event) => toggleSubmenu('showChart', event)}
                {...hoverHandlers(openSubmenu?.type === 'showChart')}
              >
                <span>Show chart</span>
                <span style={{ opacity: 0.6, fontSize: '12px' }}>▸</span>
              </button>

              <button
                type="button"
                style={{ ...baseMenuButtonStyle }}
                onClick={handleAlertsAction}
                {...hoverHandlers()}
              >
                <span>Alerts</span>
              </button>

              <button
                type="button"
                style={{
                  ...baseMenuButtonStyle,
                  fontWeight: openSubmenu?.type === 'label' ? 600 : 500,
                  background: openSubmenu?.type === 'label' ? '#f3f4f6' : 'transparent',
                }}
                onClick={(event) => toggleSubmenu('label', event)}
                {...hoverHandlers(openSubmenu?.type === 'label')}
              >
                <span>Label</span>
                <span style={{ opacity: 0.6, fontSize: '12px' }}>▸</span>
              </button>

              <div style={separatorStyle} />

              <div style={{ padding: '6px 12px', fontSize: '12px', color: '#64748b', lineHeight: 1.5 }}>
                <div>Time: {formattedTime}</div>
                <div>Price: {formattedPrice}</div>
              </div>
            </div>,
            document.body,
          )}
          {openSubmenu &&
            createPortal(
              <div
                ref={submenuRef}
                style={submenuStyle}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => e.stopPropagation()}
              >
                {openSubmenu.type === 'showChart' ? (
                  <>
                    <button
                      type="button"
                      style={{ ...baseMenuButtonStyle }}
                      onClick={() => handleShowChartVariant('put-strike')}
                      {...hoverHandlers()}
                    >
                      <span>Put strike chart</span>
                    </button>
                    <button
                      type="button"
                      style={{ ...baseMenuButtonStyle }}
                      onClick={() => handleShowChartVariant('call-strike')}
                      {...hoverHandlers()}
                    >
                      <span>Call strike chart</span>
                    </button>
                    <button
                      type="button"
                      style={{ ...baseMenuButtonStyle }}
                      onClick={() => handleShowChartVariant('straddle-strike')}
                      {...hoverHandlers()}
                    >
                      <span>Straddle</span>
                    </button>
                  </>
                ) : (
                  <>
                    {contextMenu.existingLabel && (
                      <>
                        <button
                          type="button"
                          style={{ ...baseMenuButtonStyle }}
                          onClick={() => handleShowChart(contextMenu.existingLabel!.id)}
                          {...hoverHandlers()}
                        >
                          <span>View label chart</span>
                        </button>
                        <button
                          type="button"
                          style={{ ...baseMenuButtonStyle }}
                          onClick={() => handleLabelDelete(contextMenu.existingLabel!.id)}
                          {...hoverHandlers()}
                        >
                          <span>Delete label</span>
                        </button>
                        <div style={separatorStyle} />
                      </>
                    )}
                    {LABEL_MENU_OPTIONS.map((option) => {
                      const isActive = currentLabelType === option.type
                      return (
                        <button
                          key={option.type}
                          type="button"
                          style={{
                            ...baseMenuButtonStyle,
                            fontWeight: isActive ? 600 : 500,
                            background: isActive ? '#eef2ff' : 'transparent',
                          }}
                          onClick={() => handleLabelCreate(option.type)}
                          {...hoverHandlers(isActive)}
                        >
                          <span>{option.label}</span>
                          {isActive && <span style={{ fontSize: '12px', color: '#4338ca' }}>●</span>}
                        </button>
                      )
                    })}
                    {contextMenu.existingLabel && (
                      <>
                        <div style={separatorStyle} />
                        <button
                          type="button"
                          style={{
                            ...baseMenuButtonStyle,
                            color: '#ef4444',
                          }}
                          onClick={() => handleLabelDelete(contextMenu.existingLabel!.id)}
                          {...hoverHandlers()}
                        >
                          <span>Clear label</span>
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>,
              document.body,
            )}
        </>
      )}

      {/* Label Editor (for keyboard shortcut) */}
      {labelEditor.visible && createPortal(
        <div
          ref={editorRef}
          className="absolute z-50 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4"
          style={{
            left: `${labelEditor.x}px`,
            top: `${labelEditor.y}px`
          }}
        >
          <div className="text-sm font-medium mb-3">Add Label</div>
          <div className="grid grid-cols-2 gap-2">
            <button
              className="px-3 py-2 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600"
              style={{ borderColor: LABEL_COLORS.bullish }}
              onClick={() => {
                handleLabelCreate('bullish');
                setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
              }}
            >
              Bullish
            </button>
            <button
              className="px-3 py-2 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600"
              style={{ borderColor: LABEL_COLORS.bearish }}
              onClick={() => {
                handleLabelCreate('bearish');
                setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
              }}
            >
              Bearish
            </button>
            <button
              className="px-3 py-2 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600"
              style={{ borderColor: LABEL_COLORS.neutral }}
              onClick={() => {
                handleLabelCreate('neutral');
                setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
              }}
            >
              Neutral
            </button>
            <button
              className="px-3 py-1 text-xs rounded hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600"
              onClick={() => setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 })}
            >
              Cancel (Esc)
            </button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};
