import "@testing-library/jest-dom/vitest";

class IntersectionObserverStub {
  readonly root: Element | null = null;
  readonly rootMargin = "";
  readonly thresholds: readonly number[] = [];

  constructor(private callback: (entries: Array<{ isIntersecting: boolean; target: Element }>) => void) {}

  observe(target: Element) {
    this.callback([{ isIntersecting: true, target }]);
  }

  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

Object.defineProperty(globalThis, "IntersectionObserver", {
  writable: true,
  configurable: true,
  value: IntersectionObserverStub,
});
