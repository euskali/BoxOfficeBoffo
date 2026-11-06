import { Route, Routes } from 'react-router'
import Layout from './components/Layout'
import Home from './pages/Home'
import NotFound from './pages/NotFound'
import Placeholder from './pages/Placeholder'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="films" element={<Placeholder title="Films" />} />
        <Route path="leaderboard" element={<Placeholder title="Leaderboard" />} />
        <Route path="people" element={<Placeholder title="People" />} />
        <Route path="weekend" element={<Placeholder title="Weekend Charts" />} />
        <Route path="about" element={<Placeholder title="About" />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
