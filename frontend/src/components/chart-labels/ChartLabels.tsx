import React, { useEffect, useRef, useState, useCallback } from 'react';
import { IChartApi, ISeriesApi, SeriesMarker, Time } from 'lightweight-charts';
import { createPortal } from 'react-dom';
import { Label } from '../../types/labels';

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
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  timestamp: number | null;
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

export const ChartLabels: React.FC<ChartLabelsProps> = ({
  chart,
  series,
  symbol,
  timeframe,
  labels,
  onLabelCreate,
  onLabelDelete,
  onShowChart
}) => {
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    timestamp: null
  });

  const [labelEditor, setLabelEditor] = useState<LabelEditorState>({
    visible: false,
    x: 0,
    y: 0,
    timestamp: 0
  });

  const [optimisticLabels, setOptimisticLabels] = useState<Label[]>([]);
  const contextMenuRef = useRef<HTMLDivElement>(null);
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
      
      // Check if label exists at this timestamp
      const existingLabel = labels.find(l => {
        const labelTime = new Date(l.metadata.nearest_candle_timestamp_utc).getTime() / 1000;
        return Math.abs(labelTime - timestamp) < 60; // Within 1 minute
      });

      setContextMenu({
        visible: true,
        x: event.clientX,
        y: event.clientY,
        timestamp,
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
        setContextMenu({ visible: false, x: 0, y: 0, timestamp: null });
        setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [chart, series]);

  // Close context menu on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(event.target as Node)) {
        setContextMenu({ visible: false, x: 0, y: 0, timestamp: null });
      }
      if (editorRef.current && !editorRef.current.contains(event.target as Node)) {
        setLabelEditor({ visible: false, x: 0, y: 0, timestamp: 0 });
      }
    };

    if (contextMenu.visible || labelEditor.visible) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [contextMenu.visible, labelEditor.visible]);

  const handleLabelCreate = async (labelType: Label['label_type']) => {
    if (!contextMenu.timestamp) return;

    const timestamp = new Date(contextMenu.timestamp * 1000).toISOString();
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
    setContextMenu({ visible: false, x: 0, y: 0, timestamp: null });

    try {
      await onLabelCreate(contextMenu.timestamp, labelType);
      // Remove optimistic label after successful creation
      setOptimisticLabels(prev => prev.filter(l => l.id !== optimisticId));
    } catch (error) {
      // Remove optimistic label on error
      setOptimisticLabels(prev => prev.filter(l => l.id !== optimisticId));
      console.error('Failed to create label:', error);
    }
  };

  const handleLabelDelete = async (labelId: string) => {
    setContextMenu({ visible: false, x: 0, y: 0, timestamp: null });
    
    try {
      await onLabelDelete(labelId);
    } catch (error) {
      console.error('Failed to delete label:', error);
    }
  };

  const handleShowChart = (labelId: string) => {
    setContextMenu({ visible: false, x: 0, y: 0, timestamp: null });
    onShowChart(labelId);
  };

  return (
    <>
      {/* Context Menu */}
      {contextMenu.visible && createPortal(
        <div
          ref={contextMenuRef}
          style={{
            position: 'fixed',
            left: `${Math.min(contextMenu.x, window.innerWidth - 200)}px`,
            top: `${Math.min(contextMenu.y, window.innerHeight - 300)}px`,
            background: '#ffffff',
            color: '#374151',
            border: '1px solid #ccc',
            borderRadius: '8px',
            boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
            zIndex: 2147483647,
            padding: '6px',
            minWidth: '180px',
            fontSize: '14px',
            pointerEvents: 'auto',
            userSelect: 'none'
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => { e.preventDefault(); e.stopPropagation() }}
        >
          {contextMenu.existingLabel ? (
            <>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => handleShowChart(contextMenu.existingLabel!.id)}
              >
                Show Chart
              </div>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => handleLabelDelete(contextMenu.existingLabel!.id)}
              >
                Delete Label
              </div>
              <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
              <div className="px-4 py-2 text-xs text-gray-500">
                Current: {contextMenu.existingLabel.label_type.replace('_', ' ').toUpperCase()}
              </div>
            </>
          ) : (
            <>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => { console.log('[menu] click Bullish'); handleLabelCreate('bullish') }}
              >
                ➕ Set Bullish
              </div>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => { console.log('[menu] click Bearish'); handleLabelCreate('bearish') }}
              >
                ➕ Set Bearish
              </div>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => { console.log('[menu] click Neutral'); handleLabelCreate('neutral') }}
              >
                ➕ Set Neutral
              </div>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => { console.log('[menu] click Exit Bullish'); handleLabelCreate('exit_bullish') }}
              >
                🏁 Exit Bullish
              </div>
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => { console.log('[menu] click Exit Bearish'); handleLabelCreate('exit_bearish') }}
              >
                🏁 Exit Bearish
              </div>
              <hr style={{ borderColor: '#ccc', margin: '6px 0' }} />
              <div
                style={{ 
                  padding: '8px 12px', 
                  cursor: 'pointer', 
                  color: '#ef4444',
                  borderRadius: '4px',
                  transition: 'background-color 0.15s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f3f4f6'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
                onClick={() => { console.log('[menu] click delete'); handleLabelDelete(contextMenu.existingLabel?.id || '') }}
              >
                🗑️ Clear label
              </div>
            </>
          )}
        </div>,
        document.body
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