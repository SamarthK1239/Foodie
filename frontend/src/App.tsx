import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense, lazy } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'
import Grocery from './pages/Grocery'
import RecipeDetail from './pages/RecipeDetail'
import Recipes from './pages/Recipes'
import Review from './pages/Review'
import Suggestions from './pages/Suggestions'
import { Loading } from './components/ui'

// Charting and barcode decoding each pull in a large dependency that most page
// views never need, so they load only when their route is actually opened.
const Analytics = lazy(() => import('./pages/Analytics'))
const Scan = lazy(() => import('./pages/Scan'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 10_000 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="suggestions" element={<Suggestions />} />
            <Route path="recipes" element={<Recipes />} />
            <Route path="recipes/:id" element={<RecipeDetail />} />
            <Route path="grocery" element={<Grocery />} />
            <Route path="review" element={<Review />} />
            <Route
              path="scan"
              element={
                <Suspense fallback={<Loading what="the scanner" />}>
                  <Scan />
                </Suspense>
              }
            />
            <Route
              path="analytics"
              element={
                <Suspense fallback={<Loading what="your stats" />}>
                  <Analytics />
                </Suspense>
              }
            />
            <Route path="admin" element={<Admin />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
