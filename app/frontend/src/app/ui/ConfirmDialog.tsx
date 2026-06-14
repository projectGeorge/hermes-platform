import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "default";
  isBusy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "default",
  isBusy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onCancel]);

  if (!open) return null;

  const confirmButtonClass =
    tone === "danger"
      ? "rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:opacity-50"
      : "hermes-primary-button px-4 py-2 text-sm disabled:opacity-50";

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
      role="presentation"
    >
      <div
        className="mx-4 w-full max-w-md rounded-xl border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-6 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
      >
        <h2
          className="text-base font-semibold text-[var(--hermes-text)]"
          id="confirm-dialog-title"
        >
          {title}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-[var(--hermes-muted)]">
          {description}
        </p>
        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.04]"
            disabled={isBusy}
            onClick={onCancel}
            ref={cancelRef}
            type="button"
          >
            {cancelLabel}
          </button>
          <button
            className={confirmButtonClass}
            disabled={isBusy}
            onClick={onConfirm}
            type="button"
          >
            {isBusy ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
