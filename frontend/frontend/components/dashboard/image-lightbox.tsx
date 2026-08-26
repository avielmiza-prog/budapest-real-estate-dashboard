"use client";

import Image from "next/image";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect } from "react";
import { createPortal } from "react-dom";

interface ImageLightboxProps {
  images: string[];
  index: number;
  title: string;
  onIndexChange: (index: number) => void;
  onClose: () => void;
}

export function ImageLightbox({ images, index, title, onIndexChange, onClose }: ImageLightboxProps) {
  const goPrev = () => onIndexChange((index - 1 + images.length) % images.length);
  const goNext = () => onIndexChange((index + 1) % images.length);

  useEffect(() => {
    // The underlying Radix Dialog registers its own Escape handler on
    // `document` with capture:true as soon as it opens — since that happens
    // before this lightbox mounts, a same-target capture listener here would
    // always fire second and couldn't stop it. Listening on `window` instead
    // runs first (capture order is outside-in: window before document), so
    // stopPropagation here reliably swallows the key before Radix sees it —
    // otherwise one Escape press closes both the lightbox and the modal.
    const handleKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" && e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.stopPropagation();
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", handleKey, true);
    return () => window.removeEventListener("keydown", handleKey, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, images.length]);

  if (typeof document === "undefined" || images.length === 0) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-black/95"
      role="dialog"
      aria-modal="true"
      aria-label={`${title} — full-screen photo preview`}
      onClick={onClose}
    >
      <div className="flex items-center justify-between p-4 text-white">
        <span className="text-sm">
          {index + 1} / {images.length}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full p-1.5 hover:bg-white/10"
          aria-label="Close full-screen preview"
        >
          <X className="h-6 w-6" />
        </button>
      </div>

      <div className="relative flex-1 px-4 pb-4" onClick={(e) => e.stopPropagation()}>
        <div className="relative h-full w-full">
          <Image src={images[index]!} alt={`${title} photo ${index + 1}`} fill className="object-contain" unoptimized />
        </div>

        {images.length > 1 && (
          <>
            <button
              type="button"
              onClick={goPrev}
              className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60"
              aria-label="Previous photo"
            >
              <ChevronLeft className="h-7 w-7" />
            </button>
            <button
              type="button"
              onClick={goNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60"
              aria-label="Next photo"
            >
              <ChevronRight className="h-7 w-7" />
            </button>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
