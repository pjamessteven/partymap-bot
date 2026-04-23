'use client'

import { useState, useCallback } from 'react'
import { Upload, X, ImageIcon } from 'lucide-react'

interface ImageDropzoneProps {
  value?: string
  onChange: (base64Image: string | undefined) => void
  label?: string
  accept?: string
  maxSizeMB?: number
}

export function ImageDropzone({
  value,
  onChange,
  label = 'Drop image here or click to browse',
  accept = 'image/*',
  maxSizeMB = 5,
}: ImageDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const processFile = (file: File) => {
    setError(null)

    // Check file type
    if (!file.type.startsWith('image/')) {
      setError('Please upload an image file')
      return
    }

    // Check file size
    if (file.size > maxSizeMB * 1024 * 1024) {
      setError(`File size must be less than ${maxSizeMB}MB`)
      return
    }

    // Convert to base64
    const reader = new FileReader()
    reader.onload = (e) => {
      const base64 = e.target?.result as string
      onChange(base64)
    }
    reader.onerror = () => {
      setError('Failed to read file')
    }
    reader.readAsDataURL(file)
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const file = e.dataTransfer.files[0]
    if (file) {
      processFile(file)
    }
  }, [onChange, maxSizeMB])

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      processFile(file)
    }
  }, [onChange, maxSizeMB])

  const handleRemove = () => {
    onChange(undefined)
    setError(null)
  }

  return (
    <div className="space-y-2">
      {value ? (
        <div className="relative group">
          <div className="aspect-video relative rounded-lg border overflow-hidden bg-muted">
            <img
              src={value}
              alt="Preview"
              className="w-full h-full object-contain"
            />
          </div>
          <button
            onClick={handleRemove}
            className="absolute top-2 right-2 p-1.5 bg-red-500 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity shadow-lg hover:bg-red-600"
            type="button"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <label
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`
            relative flex flex-col items-center justify-center
            w-full h-48 rounded-lg border-2 border-dashed
            cursor-pointer transition-colors
            ${isDragging
              ? 'border-primary bg-primary/5'
              : 'border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-muted/50'
            }
          `}
        >
          <div className="flex flex-col items-center justify-center space-y-2 text-muted-foreground">
            <div className="p-3 rounded-full bg-muted">
              {isDragging ? (
                <ImageIcon className="h-6 w-6 text-primary" />
              ) : (
                <Upload className="h-6 w-6" />
              )}
            </div>
            <div className="text-center">
              <p className="text-sm font-medium">{label}</p>
              <p className="text-xs text-muted-foreground mt-1">
                PNG, JPG, GIF up to {maxSizeMB}MB
              </p>
            </div>
          </div>
          <input
            type="file"
            className="hidden"
            accept={accept}
            onChange={handleFileInput}
          />
        </label>
      )}

      {error && (
        <p className="text-sm text-red-500">{error}</p>
      )}
    </div>
  )
}
