import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ProgressBar from '../ProgressBar';

describe('ProgressBar', () => {
  it('renders at 0% width', () => {
    const { container } = render(<ProgressBar progress={0} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.style.width).toBe('0%');
  });

  it('renders at 50% width', () => {
    const { container } = render(<ProgressBar progress={50} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.style.width).toBe('50%');
  });

  it('renders at 100% width', () => {
    const { container } = render(<ProgressBar progress={100} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.style.width).toBe('100%');
  });

  it('clamps values above 100 to 100%', () => {
    const { container } = render(<ProgressBar progress={150} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.style.width).toBe('100%');
  });

  it('clamps negative values to 0%', () => {
    const { container } = render(<ProgressBar progress={-20} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.style.width).toBe('0%');
  });

  it('renders the outer container as the progress track', () => {
    const { container } = render(<ProgressBar progress={50} />);
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.className).toContain('progress-track');
  });

  it('renders the fill bar with active gradient class for partial progress', () => {
    const { container } = render(<ProgressBar progress={50} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.className).toContain('progress-fill-active');
  });

  it('renders the fill bar with done gradient class at 100%', () => {
    const { container } = render(<ProgressBar progress={100} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar.className).toContain('progress-fill-done');
  });
});
