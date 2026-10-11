import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { RoleGate } from './auth/RoleGate';
import { ALL_ROLES, STAFF, homePath } from './lib/roles';
import { LoginScreen } from './screens/LoginScreen';
import { Placeholder } from './screens/Placeholder';
import { VisitsScreen } from './screens/VisitsScreen';
import { VisitScreen } from './screens/VisitScreen';

function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={user ? homePath(user.role) : '/login'} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route element={<RequireAuth />}>
        <Route path="/visits" element={<RoleGate roles={STAFF}><VisitsScreen /></RoleGate>} />
        <Route path="/visits/new" element={<RoleGate roles={STAFF}><Placeholder title="Новый заезд" /></RoleGate>} />
        <Route path="/visits/:visitId" element={<RoleGate roles={STAFF}><VisitScreen /></RoleGate>} />
        <Route path="/visits/:visitId/works/new" element={<RoleGate roles={STAFF}><Placeholder title="Новая работа" /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId" element={<RoleGate roles={ALL_ROLES}><Placeholder title="Работа" /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId/parts/new" element={<RoleGate roles={STAFF}><Placeholder title="Запчасть" /></RoleGate>} />
        <Route path="/my" element={<RoleGate roles={['mechanic']}><Placeholder title="Мои работы" /></RoleGate>} />
        <Route path="/search" element={<RoleGate roles={ALL_ROLES}><Placeholder title="Поиск" /></RoleGate>} />
        <Route path="/clients/new" element={<RoleGate roles={STAFF}><Placeholder title="Новый клиент" /></RoleGate>} />
        <Route path="/clients/:clientId" element={<RoleGate roles={STAFF}><Placeholder title="Клиент" /></RoleGate>} />
        <Route path="/vehicles/new" element={<RoleGate roles={STAFF}><Placeholder title="Новая машина" /></RoleGate>} />
        <Route path="/vehicles/:vehicleId" element={<RoleGate roles={ALL_ROLES}><Placeholder title="Машина" /></RoleGate>} />
        <Route path="/more" element={<RoleGate roles={STAFF}><Placeholder title="Ещё" /></RoleGate>} />
        <Route path="/consent/paper" element={<RoleGate roles={STAFF}><Placeholder title="Бумажное согласие" /></RoleGate>} />
        <Route path="/staff/new" element={<RoleGate roles={['admin']}><Placeholder title="Новый сотрудник" /></RoleGate>} />
        <Route path="*" element={<HomeRedirect />} />
      </Route>
    </Routes>
  );
}
