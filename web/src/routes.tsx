import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { RoleGate } from './auth/RoleGate';
import { AddPartForm } from './forms/AddPartForm';
import { AddWorkForm } from './forms/AddWorkForm';
import { ALL_ROLES, STAFF, homePath } from './lib/roles';
import { ClientScreen } from './screens/ClientScreen';
import { LoginScreen } from './screens/LoginScreen';
import { MyWorksScreen } from './screens/MyWorksScreen';
import { Placeholder } from './screens/Placeholder';
import { SearchScreen } from './screens/SearchScreen';
import { VehicleScreen } from './screens/VehicleScreen';
import { VisitsScreen } from './screens/VisitsScreen';
import { VisitScreen } from './screens/VisitScreen';
import { WorkScreen } from './screens/WorkScreen';

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
        <Route path="/visits/:visitId/works/new" element={<RoleGate roles={STAFF}><AddWorkForm /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId" element={<RoleGate roles={ALL_ROLES}><WorkScreen /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId/parts/new" element={<RoleGate roles={STAFF}><AddPartForm /></RoleGate>} />
        <Route path="/my" element={<RoleGate roles={['mechanic']}><MyWorksScreen /></RoleGate>} />
        <Route path="/search" element={<RoleGate roles={ALL_ROLES}><SearchScreen /></RoleGate>} />
        <Route path="/clients/new" element={<RoleGate roles={STAFF}><Placeholder title="Новый клиент" /></RoleGate>} />
        <Route path="/clients/:clientId" element={<RoleGate roles={STAFF}><ClientScreen /></RoleGate>} />
        <Route path="/vehicles/new" element={<RoleGate roles={STAFF}><Placeholder title="Новая машина" /></RoleGate>} />
        <Route path="/vehicles/:vehicleId" element={<RoleGate roles={ALL_ROLES}><VehicleScreen /></RoleGate>} />
        <Route path="/more" element={<RoleGate roles={STAFF}><Placeholder title="Ещё" /></RoleGate>} />
        <Route path="/consent/paper" element={<RoleGate roles={STAFF}><Placeholder title="Бумажное согласие" /></RoleGate>} />
        <Route path="/staff/new" element={<RoleGate roles={['admin']}><Placeholder title="Новый сотрудник" /></RoleGate>} />
        <Route path="*" element={<HomeRedirect />} />
      </Route>
    </Routes>
  );
}
