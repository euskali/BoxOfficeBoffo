import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import App from './App'
import Home from './pages/Home'

describe('Home', () => {
  it('renders the Hello 1999 heading and a 9-row milestone table', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Hello 1999' })).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Construction progress' })
    const body = table.querySelector('tbody')!
    expect(within(body).getAllByRole('row')).toHaveLength(9)
  })
})

describe('App routing', () => {
  it('renders the home page at /', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Hello 1999' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('contentinfo')).toHaveTextContent('Last updated:')
  })

  it('renders a placeholder for known sections', () => {
    render(
      <MemoryRouter initialEntries={['/films']}>
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Under construction')
  })

  it('renders the 404 page for unknown routes', () => {
    render(
      <MemoryRouter initialEntries={['/no/such/page']}>
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: /404/ })).toBeInTheDocument()
  })
})
