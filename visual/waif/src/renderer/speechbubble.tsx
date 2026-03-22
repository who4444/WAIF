import { useEffect, useState } from 'react'

interface Props {
  text: string
  chibiX: number
  chibiY: number
  visible: boolean
}

export default function SpeechBubble({ text, chibiX, chibiY, visible }: Props) {
  const [opacity, setOpacity] = useState(0)
  const [scale, setScale] = useState(0.8)

  useEffect(() => {
    if (visible) {
      setOpacity(1)
      setScale(1)
    } else {
      setOpacity(0)
      setScale(0.95)
    }
  }, [visible])

  // guard against NaN before any math
  const safeX = isNaN(chibiX) ? window.innerWidth / 2 : chibiX
  const safeY = isNaN(chibiY) ? 100 : chibiY

  const onRightSide = safeX > window.innerWidth / 2
  const bubbleLeft = onRightSide ? safeX - 220 : safeX + 60
  const bubbleBottom = safeY + 60

  return (
    <div style={{
      position: 'fixed',
      left: bubbleLeft,
      bottom: bubbleBottom,
      maxWidth: 200,
      padding: '10px 14px',
      background: 'rgba(255,255,255,0.95)',
      borderRadius: onRightSide ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
      fontSize: 13,
      lineHeight: 1.5,
      color: '#1a1a2e',
      pointerEvents: 'none',
      opacity,
      transform: `scale(${scale})`,
      transformOrigin: onRightSide ? 'bottom right' : 'bottom left',
      transition: 'opacity 0.2s ease, transform 0.2s ease',
      boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
      zIndex: 20,
    }}>
      {text}
    </div>
  )
}