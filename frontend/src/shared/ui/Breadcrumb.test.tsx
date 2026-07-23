import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Breadcrumb } from './Breadcrumb';

function renderBreadcrumb(items: { label: string; to?: string }[]) {
  return render(
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Breadcrumb items={items} />
    </BrowserRouter>,
  );
}

describe('Breadcrumb', () => {
  it('should render nothing when items array is empty', () => {
    const { container } = renderBreadcrumb([]);
    expect(container.querySelector('nav')).toBeNull();
  });

  it('should render nothing for a single-item trail (duplicates the top bar)', () => {
    // The top app bar already shows the active module icon + name, so a
    // lone module label adds no navigation depth (MODULE_STYLE_GUIDE 2.1).
    const { container } = renderBreadcrumb([{ label: 'Current Page' }]);
    expect(container.querySelector('nav')).toBeNull();
  });

  it('should render home icon link when the trail has depth', () => {
    renderBreadcrumb([{ label: 'Projects', to: '/projects' }, { label: 'Page' }]);
    const homeLink = screen.getByLabelText('Dashboard');
    expect(homeLink).toBeInTheDocument();
    expect(homeLink).toHaveAttribute('href', '/');
  });

  it('should render intermediate items as links', () => {
    renderBreadcrumb([
      { label: 'Projects', to: '/projects' },
      { label: 'My Project' },
    ]);
    const link = screen.getByText('Projects');
    expect(link.closest('a')).toHaveAttribute('href', '/projects');
    // Last item should not be a link
    expect(screen.getByText('My Project').closest('a')).toBeNull();
  });

  it('should render three-level breadcrumb', () => {
    renderBreadcrumb([
      { label: 'Projects', to: '/projects' },
      { label: 'Project A', to: '/projects/1' },
      { label: 'BOQ Editor' },
    ]);
    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('Project A')).toBeInTheDocument();
    expect(screen.getByText('BOQ Editor')).toBeInTheDocument();
  });
});
