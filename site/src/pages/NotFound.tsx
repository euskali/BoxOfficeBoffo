import { Link } from 'react-router'
import SectionBar from '../components/SectionBar'

export default function NotFound() {
  return (
    <>
      <SectionBar>Error 404</SectionBar>
      <h1>404: Page not found</h1>
      <p>
        We looked everywhere, even behind the sofa, and this page is not here. Maybe it was never
        released.
      </p>
      <p>
        <Link to="/">Return to the home page</Link>
      </p>
    </>
  )
}
