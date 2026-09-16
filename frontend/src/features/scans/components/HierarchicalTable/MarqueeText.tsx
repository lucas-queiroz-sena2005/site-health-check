import React, { useRef, useState, useEffect, useId } from 'react'

export interface MarqueeTextProps {
  children: React.ReactNode
  className?: string
}

export function MarqueeText({ children, className = '' }: MarqueeTextProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const slidingRef = useRef<HTMLDivElement>(null)
  const [isOverflowing, setIsOverflowing] = useState(false)
  const [scrollAmount, setScrollAmount] = useState(0)
  const uniqueId = useId().replace(/:/g, '')

  useEffect(() => {
    const checkOverflow = () => {
      if (containerRef.current && slidingRef.current) {
        const containerWidth = containerRef.current.clientWidth
        const textWidth = slidingRef.current.scrollWidth
        
        if (textWidth > containerWidth) {
          setIsOverflowing(true)
          setScrollAmount(textWidth - containerWidth + 20) 
        } else {
          setIsOverflowing(false)
          setScrollAmount(0)
        }
      }
    }

    checkOverflow()
    const observer = new ResizeObserver(checkOverflow)
    if (containerRef.current) {
      observer.observe(containerRef.current)
    }

    return () => observer.disconnect()
  }, [children])

  return (
    <div 
      ref={containerRef}
      className={`relative flex overflow-hidden w-full ${className}`}
      title={typeof children === 'string' ? children : undefined}
    >
      {/* Static truncated version */}
      <div 
        className={`marquee-static-${uniqueId} whitespace-nowrap truncate w-full`}
        style={{ transition: 'opacity 0.2s ease-in-out' }}
      >
        {children}
      </div>
      
      {/* Sliding absolute version */}
      <div 
        ref={slidingRef}
        className={`marquee-sliding-${uniqueId} absolute top-0 left-0 whitespace-nowrap pointer-events-none opacity-0`}
        style={{
          transition: 'transform 2s linear, opacity 0.2s ease-in-out'
        }}
      >
        {children}
      </div>

      {isOverflowing && (
        <style dangerouslySetInnerHTML={{__html: `
          .group:hover .marquee-static-${uniqueId} {
             opacity: 0 !important;
          }
          .group:hover .marquee-sliding-${uniqueId} {
             opacity: 1 !important;
             transform: translateX(-${scrollAmount}px) !important;
          }
        `}} />
      )}
    </div>
  )
}
