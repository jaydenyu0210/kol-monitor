'use client'

import { useEffect, useRef } from 'react'
import { api } from '@/lib/api-client'

/**
 * Invisible component that auto-detects the browser timezone
 * and saves it to the backend if the user hasn't set one yet.
 * Renders nothing — just runs once on mount.
 */
export default function TimezoneSync() {
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (!detected) return

    api.getSettings()
      .then((s: any) => {
        // Only auto-save if no timezone has been explicitly saved
        if (!s.timezone) {
          api.saveTimezone(detected).catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  return null
}
