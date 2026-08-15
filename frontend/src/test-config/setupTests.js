import '@testing-library/jest-dom';

// ---------------------------------------------------------------------------
// Recharts in jsdom
// ---------------------------------------------------------------------------
// Every chart in the app is wrapped in a Recharts <ResponsiveContainer>, which
// sizes itself from the DOM. jsdom reports 0x0 for every element and has no
// ResizeObserver, so the container renders an empty <div> and nothing inside
// the chart — no bars, no labels, no <text> nodes. That made assertions like
// `findByText('BTC')` fail even though the component was working correctly.
//
// Stubbing ResizeObserver and giving elements a non-zero measured size makes
// charts render their contents headlessly. Both stubs are test-only.

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (!global.ResizeObserver) {
  global.ResizeObserver = ResizeObserverStub;
}

const CHART_WIDTH = 800;
const CHART_HEIGHT = 400;

Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
  configurable: true,
  value: CHART_WIDTH,
});
Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
  configurable: true,
  value: CHART_HEIGHT,
});
Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value() {
    return {
      width: CHART_WIDTH,
      height: CHART_HEIGHT,
      top: 0,
      left: 0,
      bottom: CHART_HEIGHT,
      right: CHART_WIDTH,
      x: 0,
      y: 0,
      toJSON: () => {},
    };
  },
});
