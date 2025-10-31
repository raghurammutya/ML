import React from 'react'
import type { ReplayControls as IReplayControls } from '../../types/replay'

interface ReplayControlsProps {
  controls: IReplayControls
  isPlaying: boolean
  currentSpeed: number
  speedPresets: number[]
  cursorTime: string | null
  isEndOfData: boolean
}

const ReplayControls: React.FC<ReplayControlsProps> = ({
  controls,
  isPlaying,
  currentSpeed,
  speedPresets,
  cursorTime,
  isEndOfData
}) => {
  const formatTime = (isoString: string | null) => {
    if (!isoString) return '--:--'
    const date = new Date(isoString)
    return date.toLocaleString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      day: '2-digit',
      month: 'short',
      hour12: false,
      timeZone: 'Asia/Kolkata'
    })
  }

  return (
    <div className="replay-controls">
      <div className="replay-controls__toolbar">
        {/* Time badge */}
        <div className="replay-controls__time-badge">
          {formatTime(cursorTime)}
        </div>

        {/* Rewind */}
        <button
          className="replay-controls__btn"
          onClick={controls.rewind}
          title="Rewind 1 minute"
        >
          ⏮
        </button>

        {/* Step Back */}
        <button
          className="replay-controls__btn"
          onClick={controls.stepBackward}
          title="Step back one candle"
        >
          ⏪
        </button>

        {/* Play/Pause */}
        <button
          className="replay-controls__btn replay-controls__btn--primary"
          onClick={isPlaying ? controls.pause : controls.play}
          disabled={isEndOfData}
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? '⏸' : '▶️'}
        </button>

        {/* Step Forward */}
        <button
          className="replay-controls__btn"
          onClick={controls.stepForward}
          disabled={isEndOfData}
          title="Step forward one candle"
        >
          ⏩
        </button>

        {/* Fast Forward */}
        <button
          className="replay-controls__btn"
          onClick={controls.fastForward}
          disabled={isEndOfData}
          title="Fast forward 1 minute"
        >
          ⏭
        </button>

        {/* Speed selector */}
        <div className="replay-controls__speed">
          <button
            className="replay-controls__speed-btn"
            onClick={() => {
              const currentIndex = speedPresets.indexOf(currentSpeed)
              if (currentIndex > 0) {
                controls.setSpeed(speedPresets[currentIndex - 1])
              }
            }}
            disabled={speedPresets.indexOf(currentSpeed) === 0}
          >
            −
          </button>
          <span className="replay-controls__speed-value">{currentSpeed}x</span>
          <button
            className="replay-controls__speed-btn"
            onClick={() => {
              const currentIndex = speedPresets.indexOf(currentSpeed)
              if (currentIndex < speedPresets.length - 1) {
                controls.setSpeed(speedPresets[currentIndex + 1])
              }
            }}
            disabled={speedPresets.indexOf(currentSpeed) === speedPresets.length - 1}
          >
            +
          </button>
        </div>

        {/* Exit */}
        <button
          className="replay-controls__btn replay-controls__btn--exit"
          onClick={controls.exit}
          title="Exit replay mode"
        >
          ✖️
        </button>

        {isEndOfData && (
          <span className="replay-controls__end-badge">End of Data</span>
        )}
      </div>
    </div>
  )
}

export default ReplayControls
