import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../Layout';

function renderLayout(children: React.ReactNode = <div>test content</div>) {
  return render(
    <MemoryRouter>
      <Layout>{children}</Layout>
    </MemoryRouter>,
  );
}

describe('Layout', () => {
  it('renders the ARCHITECT title', () => {
    renderLayout();
    expect(screen.getByText('ARCHITECT')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderLayout();
    expect(screen.getByText('Autonomous Coding System')).toBeInTheDocument();
  });

  it('renders Tasks navigation link', () => {
    renderLayout();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
  });

  it('renders Health navigation link', () => {
    renderLayout();
    expect(screen.getByText('Health')).toBeInTheDocument();
  });

  it('renders Proposals navigation link', () => {
    renderLayout();
    expect(screen.getByText('Proposals')).toBeInTheDocument();
  });

  it('renders navigation links with correct hrefs', () => {
    renderLayout();
    const tasksLink = screen.getByText('Tasks').closest('a');
    const healthLink = screen.getByText('Health').closest('a');
    const proposalsLink = screen.getByText('Proposals').closest('a');

    expect(tasksLink).toHaveAttribute('href', '/tasks');
    expect(healthLink).toHaveAttribute('href', '/health');
    expect(proposalsLink).toHaveAttribute('href', '/proposals');
  });

  it('renders children content in the main area', () => {
    renderLayout(<p>My child content</p>);
    expect(screen.getByText('My child content')).toBeInTheDocument();
  });

  it('renders the version footer', () => {
    renderLayout();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
  });
});
