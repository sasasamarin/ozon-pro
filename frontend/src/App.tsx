import { Routes, Route, Navigate } from 'react-router-dom'
import { Login } from '@/pages/Login'
import { Register } from '@/pages/Register'
import { Dashboard } from '@/pages/Dashboard'
import { Cabinets } from '@/pages/Cabinets'
import { CabinetNew } from '@/pages/CabinetNew'
import { Settings } from '@/pages/Settings'
import { AppLayout } from '@/components/AppLayout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { PagePlaceholder } from '@/components/PagePlaceholder'
import { getAllPlaceholderItems } from '@/lib/menu'

export default function App() {
  const placeholderItems = getAllPlaceholderItems()

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/cabinets" element={<Cabinets />} />
        <Route path="/cabinets/new" element={<CabinetNew />} />
        <Route path="/settings" element={<Settings />} />

        {placeholderItems.map((item) => (
          <Route
            key={item.path}
            path={item.path}
            element={
              <PagePlaceholder
                icon={item.icon}
                title={item.label}
                description={item.placeholder!.description}
                plannedFeatures={item.placeholder!.plannedFeatures}
              />
            }
          />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
