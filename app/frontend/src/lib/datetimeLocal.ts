import type {
  ClipboardEvent,
  DragEvent,
  KeyboardEvent,
  MouseEvent,
} from "react";

type PickerInputElement = HTMLInputElement & {
  showPicker?: () => void;
};

function normalizeDateTimeValue(value: string): string {
  return value.trim().replace(" ", "T");
}

function openPicker(target: HTMLInputElement) {
  (target as PickerInputElement).showPicker?.();
}

export function toDateTimeLocalInputValue(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  return normalizeDateTimeValue(value).slice(0, 16);
}

export function toDateTimeLocalApiValue(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = normalizeDateTimeValue(value);
  return normalized ? normalized.slice(0, 16) : null;
}

export function openDateTimeLocalPicker(event: MouseEvent<HTMLInputElement>) {
  openPicker(event.currentTarget);
}

export function handleDateTimeLocalKeyDown(event: KeyboardEvent<HTMLInputElement>) {
  if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
    event.preventDefault();
    openPicker(event.currentTarget);
    return;
  }

  if (event.key.length === 1) {
    event.preventDefault();
  }
}

export function preventDateTimeLocalPaste(
  event: ClipboardEvent<HTMLInputElement> | DragEvent<HTMLInputElement>,
) {
  event.preventDefault();
}
