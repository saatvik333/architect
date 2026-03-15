import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { usePolling } from '../usePolling';

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in loading state', () => {
    const fetcher = vi.fn((_signal: AbortSignal) => new Promise<string>(() => {}));
    const { result } = renderHook(() => usePolling(fetcher, 5000));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('resolves data from fetcher', async () => {
    const fetcher = vi.fn((_signal: AbortSignal) => Promise.resolve('hello'));
    const { result } = renderHook(() => usePolling(fetcher, 5000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.data).toBe('hello');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets error when fetcher rejects', async () => {
    const fetcher = vi.fn((_signal: AbortSignal) => Promise.reject(new Error('fail')));
    const { result } = renderHook(() => usePolling(fetcher, 5000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error!.message).toBe('fail');
    expect(result.current.loading).toBe(false);
  });

  it('calls fetcher again after interval', async () => {
    const fetcher = vi.fn((_signal: AbortSignal) => Promise.resolve('data'));
    renderHook(() => usePolling(fetcher, 3000));

    // Resolve the initial fetch
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    // Advance past the polling interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('cleans up interval on unmount', async () => {
    const fetcher = vi.fn((_signal: AbortSignal) => Promise.resolve('data'));
    const { unmount } = renderHook(() => usePolling(fetcher, 3000));

    // Resolve the initial fetch
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    unmount();

    // Advance timer — fetcher should not be called again
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('wraps non-Error rejections as Error objects', async () => {
    const fetcher = vi.fn((_signal: AbortSignal) => Promise.reject('string error'));
    const { result } = renderHook(() => usePolling(fetcher, 5000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error!.message).toBe('string error');
  });

  it('performs initial fetch immediately', () => {
    const fetcher = vi.fn((_signal: AbortSignal) => new Promise<string>(() => {}));
    renderHook(() => usePolling(fetcher, 5000));

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('passes AbortSignal to fetcher', () => {
    const fetcher = vi.fn((_signal: AbortSignal) => new Promise<string>(() => {}));
    renderHook(() => usePolling(fetcher, 5000));

    expect(fetcher).toHaveBeenCalledTimes(1);
    const signal = fetcher.mock.calls[0][0];
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
  });

  it('aborts in-flight request on unmount', async () => {
    const fetcher = vi.fn((_signal: AbortSignal) => Promise.resolve('data'));
    const { unmount } = renderHook(() => usePolling(fetcher, 3000));

    // Resolve the initial fetch
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Start a new fetch cycle that will be in-flight during unmount
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    const lastCallSignal = fetcher.mock.calls[fetcher.mock.calls.length - 1][0] as AbortSignal;

    unmount();

    expect(lastCallSignal.aborted).toBe(true);
  });
});
