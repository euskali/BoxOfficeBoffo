import { Link } from 'react-router'
import SectionBar from '../components/SectionBar'

export default function Placeholder({ title }: { title: string }) {
  return (
    <>
      <SectionBar>{title}</SectionBar>
      <h1>{title}: Under construction</h1>
      <p>
        This page is still being built. The time machine is warming up, so please check back
        later.
      </p>
      <p>
        <Link to="/">Back to the home page</Link>
      </p>
    </>
  )
}
