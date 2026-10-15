import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { RoleGate } from './auth/RoleGate';
import { AddPartForm } from './forms/AddPartForm';
import { AddWorkForm } from './forms/AddWorkForm';
import { NewVisitWizard } from './forms/NewVisitWizard';
import { NewClientRoute, NewVehicleRoute } from './forms/entryRoutes';
import { PaperConsentForm } from './forms/PaperConsentForm';
import { StaffForm } from './forms/StaffForm';
import { ALL_ROLES, STAFF, WORKERS, homePath } from './lib/roles';
import { ClientScreen } from './screens/ClientScreen';
import { LoginScreen } from './screens/LoginScreen';
import { MoreScreen } from './screens/MoreScreen';
import { ArchiveScreen } from './screens/ArchiveScreen';
import { BoardScreen } from './screens/BoardScreen';
import { DoneWorksScreen } from './screens/DoneWorksScreen';
import { MyWorksScreen } from './screens/MyWorksScreen';
import { StatsScreen } from './screens/StatsScreen';
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
        <Route path="/visits/archive" element={<RoleGate roles={STAFF}><ArchiveScreen /></RoleGate>} />
        <Route path="/works" element={<RoleGate roles={STAFF}><BoardScreen /></RoleGate>} />
        <Route path="/visits/new" element={<RoleGate roles={STAFF}><NewVisitWizard /></RoleGate>} />
        <Route path="/visits/:visitId" element={<RoleGate roles={STAFF}><VisitScreen /></RoleGate>} />
        <Route path="/visits/:visitId/works/new" element={<RoleGate roles={STAFF}><AddWorkForm /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId" element={<RoleGate roles={ALL_ROLES}><WorkScreen /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId/parts/new" element={<RoleGate roles={STAFF}><AddPartForm /></RoleGate>} />
        <Route path="/my" element={<RoleGate roles={WORKERS}><MyWorksScreen /></RoleGate>} />
        <Route path="/my/done" element={<RoleGate roles={WORKERS}><DoneWorksScreen /></RoleGate>} />
        <Route path="/stats" element={<RoleGate roles={ALL_ROLES}><StatsScreen /></RoleGate>} />
        <Route path="/search" element={<RoleGate roles={ALL_ROLES}><SearchScreen /></RoleGate>} />
        <Route path="/clients/new" element={<RoleGate roles={STAFF}><NewClientRoute /></RoleGate>} />
        <Route path="/clients/:clientId" element={<RoleGate roles={STAFF}><ClientScreen /></RoleGate>} />
        <Route path="/vehicles/new" element={<RoleGate roles={STAFF}><NewVehicleRoute /></RoleGate>} />
        <Route path="/vehicles/:vehicleId" element={<RoleGate roles={ALL_ROLES}><VehicleScreen /></RoleGate>} />
        <Route path="/more" element={<RoleGate roles={STAFF}><MoreScreen /></RoleGate>} />
        <Route path="/consent/paper" element={<RoleGate roles={STAFF}><PaperConsentForm /></RoleGate>} />
        <Route path="/staff/new" element={<RoleGate roles={['admin']}><StaffForm /></RoleGate>} />
        <Route path="*" element={<HomeRedirect />} />
      </Route>
    </Routes>
  );
}
