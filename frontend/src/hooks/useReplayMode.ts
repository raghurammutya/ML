import { useState, useCallback, useRef, useEffect } from 'react'
import type { ReplayState, ReplayControls } from '../types/replay'
import { fetchReplayWindow } from '../services/replay'

const SPEED_PRESETS = [0.1, 0.2, 0.5, 1, 2, 5, 10]

export function useReplayMode(
  underlying: string,
  timeframe: string,
  expiries: string[],
  panels: string[]
) {
  const [state, setState] = useState<ReplayState>({
    isActive: false,
    cursorUtc: null,
    timeframe,
    playbackSpeed: 1,
    isPlaying: false,
    isFollowingMain: false,
    windowStartUtc: null,
    windowEndUtc: null,
    availableRange: null,
    bufferedData: null
  })

  const playIntervalRef = useRef<number | null>(null)

  // Enter replay mode - fetch historical window
  const enter = useCallback(async () => {
    const now = new Date()
    const end = now.toISOString()
    const start = new Date(now.getTime() - 6 * 60 * 60 * 1000).toISOString() // 6 hours back

    try {
      const data = await fetchReplayWindow({
        underlying,
        timeframe,
        start,
        end,
        expiries,
        panels
      })

      setState(prev => ({
        ...prev,
        isActive: true,
        cursorUtc: data.timestamps[0] || null,
        windowStartUtc: data.range.start,
        windowEndUtc: data.range.end,
        availableRange: {
          earliestUtc: data.range.start,
          latestUtc: data.range.end
        },
        bufferedData: {
          timestamps: data.timestamps,
          candles: data.priceSeries.candles,
          panels: data.panels
        }
      }))
    } catch (error) {
      console.error('[Replay] Failed to fetch window:', error)
    }
  }, [underlying, timeframe, expiries, panels])

  // Exit replay mode
  const exit = useCallback(() => {
    if (playIntervalRef.current) {
      clearInterval(playIntervalRef.current)
      playIntervalRef.current = null
    }

    setState({
      isActive: false,
      cursorUtc: null,
      timeframe,
      playbackSpeed: 1,
      isPlaying: false,
      isFollowingMain: false,
      windowStartUtc: null,
      windowEndUtc: null,
      availableRange: null,
      bufferedData: null
    })
  }, [timeframe])

  // Play - advance cursor at playback speed
  const play = useCallback(() => {
    if (!state.bufferedData || !state.cursorUtc) return

    setState(prev => ({ ...prev, isPlaying: true }))

    const baseInterval = 1000 // 1 second real time = 1 timeframe unit
    const interval = baseInterval / state.playbackSpeed

    if (playIntervalRef.current) {
      clearInterval(playIntervalRef.current)
    }

    playIntervalRef.current = window.setInterval(() => {
      setState(prev => {
        if (!prev.bufferedData || !prev.cursorUtc) return prev

        const currentIndex = prev.bufferedData.timestamps.indexOf(prev.cursorUtc)
        if (currentIndex === -1 || currentIndex >= prev.bufferedData.timestamps.length - 1) {
          // End of data
          if (playIntervalRef.current) {
            clearInterval(playIntervalRef.current)
            playIntervalRef.current = null
          }
          return { ...prev, isPlaying: false }
        }

        const nextIndex = currentIndex + 1
        return {
          ...prev,
          cursorUtc: prev.bufferedData.timestamps[nextIndex]
        }
      })
    }, interval)
  }, [state.bufferedData, state.cursorUtc, state.playbackSpeed])

  // Pause
  const pause = useCallback(() => {
    if (playIntervalRef.current) {
      clearInterval(playIntervalRef.current)
      playIntervalRef.current = null
    }
    setState(prev => ({ ...prev, isPlaying: false }))
  }, [])

  // Step forward
  const stepForward = useCallback(() => {
    setState(prev => {
      if (!prev.bufferedData || !prev.cursorUtc) return prev

      const currentIndex = prev.bufferedData.timestamps.indexOf(prev.cursorUtc)
      if (currentIndex === -1 || currentIndex >= prev.bufferedData.timestamps.length - 1) {
        return prev
      }

      return {
        ...prev,
        cursorUtc: prev.bufferedData.timestamps[currentIndex + 1]
      }
    })
  }, [])

  // Step backward
  const stepBackward = useCallback(() => {
    setState(prev => {
      if (!prev.bufferedData || !prev.cursorUtc) return prev

      const currentIndex = prev.bufferedData.timestamps.indexOf(prev.cursorUtc)
      if (currentIndex <= 0) return prev

      return {
        ...prev,
        cursorUtc: prev.bufferedData.timestamps[currentIndex - 1]
      }
    })
  }, [])

  // Seek to specific timestamp
  const seek = useCallback((timestamp: string) => {
    pause()
    setState(prev => ({ ...prev, cursorUtc: timestamp }))
  }, [pause])

  // Set playback speed
  const setSpeed = useCallback((speed: number) => {
    const validSpeed = SPEED_PRESETS.includes(speed) ? speed : 1
    setState(prev => ({ ...prev, playbackSpeed: validSpeed }))

    // If currently playing, restart with new speed
    if (state.isPlaying) {
      pause()
      setTimeout(() => play(), 100)
    }
  }, [state.isPlaying, pause, play])

  // Rewind - jump back 1 minute
  const rewind = useCallback(() => {
    setState(prev => {
      if (!prev.bufferedData || !prev.cursorUtc) return prev

      const currentIndex = prev.bufferedData.timestamps.indexOf(prev.cursorUtc)
      const jumpIndex = Math.max(0, currentIndex - 60) // 60 bars = 1 minute for 1s timeframe

      return {
        ...prev,
        cursorUtc: prev.bufferedData.timestamps[jumpIndex]
      }
    })
  }, [])

  // Fast forward - jump forward 1 minute
  const fastForward = useCallback(() => {
    setState(prev => {
      if (!prev.bufferedData || !prev.cursorUtc) return prev

      const currentIndex = prev.bufferedData.timestamps.indexOf(prev.cursorUtc)
      const jumpIndex = Math.min(
        prev.bufferedData.timestamps.length - 1,
        currentIndex + 60
      )

      return {
        ...prev,
        cursorUtc: prev.bufferedData.timestamps[jumpIndex]
      }
    })
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
      }
    }
  }, [])

  const controls: ReplayControls = {
    enter,
    exit,
    play,
    pause,
    stepForward,
    stepBackward,
    seek,
    setSpeed,
    rewind,
    fastForward
  }

  return { state, controls, speedPresets: SPEED_PRESETS }
}
