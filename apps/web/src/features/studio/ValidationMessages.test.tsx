import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ValidationMessages } from './ValidationMessages'
import type { ValidationReport } from '../../api/types'
// Real responses captured from POST /api/v1/scenarios/validate (services/api, ac-dc-meshed).
import semantic from '../../test/fixtures/validation-semantic-errors.json'
import schema from '../../test/fixtures/validation-schema-errors.json'

describe('ValidationMessages', () => {
  it('renders semantic errors with path, code and message, and warnings separately', () => {
    render(<ValidationMessages report={semantic as ValidationReport} local={[]} pending={false} />)
    expect(screen.getByTestId('validation-status')).toHaveAttribute('data-valid', 'false')
    expect(screen.getByTestId('validation-status')).toHaveTextContent('2 errors')
    const errors = screen.getAllByTestId('validation-error')
    expect(errors).toHaveLength(2)
    expect(errors[0]).toHaveTextContent('events[0].asset_id')
    expect(errors[0]).toHaveTextContent('[unknown_asset]')
    expect(errors[0]).toHaveTextContent("no line with id 'nope' in network 'ac-dc-meshed'")
    expect(errors[1]).toHaveTextContent('window [2, 40) is not inside horizon [0, 10)')
    expect(screen.getAllByTestId('validation-warning')[0]).toHaveTextContent('dataset_unpinned')
  })

  it('renders schema errors', () => {
    render(<ValidationMessages report={schema as ValidationReport} local={[]} pending={false} />)
    expect(screen.getAllByTestId('validation-error')).toHaveLength(3)
    expect(screen.getByText(/less than or equal to 8784/)).toBeInTheDocument()
  })

  it('never claims validity while the backend has not answered', () => {
    render(<ValidationMessages report={null} local={['Scenario name is required.']} pending />)
    expect(screen.queryByTestId('validation-status')).toBeNull()
    expect(screen.getByText('Validating against the network…')).toBeInTheDocument()
    expect(screen.getByTestId('validation-error')).toHaveTextContent('Scenario name is required.')
  })

  it('shows a valid report with its warning count', () => {
    const report: ValidationReport = { ...(semantic as ValidationReport), valid: true, errors: [] }
    render(<ValidationMessages report={report} local={[]} pending={false} />)
    expect(screen.getByTestId('validation-status')).toHaveTextContent('Valid with 1 warning')
  })
})
