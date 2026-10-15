import { buildQuery } from '../lib/query';
import { api } from './client';
import type {
  AuthResponse, BoardList, BoardParams, CatalogItem, Client, DoneWorkList, MineSort, MyWorkItem, PartItem, PartItemCreate, RecentView, SearchHit,
  User, UserCreate, Vehicle, VehicleCreate, Visit, VisitCreate, MechanicVisit, VisitLines, VisitList, VisitListParams, VisitStatus, WorkCategory, WorkHistory,
  WorkItem, WorkItemCreate, WorkItemStatus, Stats, StatsPeriod, StatsSection,
  MechanicPay, PayScheme, VisibilitySettings,
} from './types';

const q = encodeURIComponent;

export const authApi = {
  telegram: (initData: string) => api.post<AuthResponse>('/auth/telegram', { init_data: initData }),
  devUsers: () => api.get<User[]>('/auth/dev-users'),
  devLogin: (userId: string) => api.post<AuthResponse>('/auth/dev-login', { user_id: userId }),
  me: () => api.get<User>('/auth/me'),
};

export const visitsApi = {
  list: (params: VisitListParams) => api.get<VisitList>(`/visits${buildQuery({ ...params })}`),
  listForClient: (clientId: string) => api.get<VisitList>(`/visits?client_id=${q(clientId)}`),
  listForVehicle: (vehicleId: string) => api.get<VisitList>(`/visits?vehicle_id=${q(vehicleId)}`),
  get: (id: string) => api.get<Visit>(`/visits/${id}`),
  lines: (id: string) => api.get<VisitLines>(`/visits/${id}/lines`),
  mechanicView: (id: string) => api.get<MechanicVisit>(`/visits/${id}/mechanic-view`),
  create: (body: VisitCreate) => api.post<Visit>('/visits', body),
  changeStatus: (id: string, newStatus: VisitStatus, reason: string | null = null) =>
    api.patch<Visit>(`/visits/${id}/status`, { new_status: newStatus, reason }),
  /** Signed link (5 min) that downloads the visit's PDF without an Authorization header. */
  documentLink: (id: string) => api.post<{ url: string; expires_in: number }>(`/visits/${id}/document/link`),
};

export const workItemsApi = {
  list: (visitId: string) => api.get<WorkItem[]>(`/visits/${visitId}/work-items`),
  mine: (params: { status?: WorkItemStatus[]; sort?: MineSort } = {}) =>
    api.get<MyWorkItem[]>(`/work-items/mine${buildQuery(params)}`),
  done: (params: { since?: string; outcome?: 'issued' | 'cancelled' } = {}) =>
    api.get<DoneWorkList>(`/work-items/mine/done${buildQuery(params)}`),
  board: (params: BoardParams = {}) => api.get<BoardList>(`/work-items/board${buildQuery({ ...params })}`),
  add: (visitId: string, body: WorkItemCreate) => api.post<WorkItem>(`/visits/${visitId}/work-items`, body),
  changeStatus: (visitId: string, itemId: string, newStatus: WorkItemStatus) =>
    api.patch<WorkItem>(`/visits/${visitId}/work-items/${itemId}/status`, { new_status: newStatus }),
  assign: (visitId: string, itemId: string, mechanicId: string | null) =>
    api.patch<WorkItem>(`/visits/${visitId}/work-items/${itemId}/mechanic`, { assigned_mechanic_id: mechanicId }),
  approve: (visitId: string, itemId: string) =>
    api.post<WorkItem>(`/visits/${visitId}/work-items/${itemId}/approve`),
  addPart: (visitId: string, body: PartItemCreate) => api.post<PartItem>(`/visits/${visitId}/part-items`, body),
};

export const clientsApi = {
  get: (id: string) => api.get<Client>(`/clients/${id}`),
  vehicles: (id: string) => api.get<Vehicle[]>(`/clients/${id}/vehicles`),
  create: (fullName: string, phone: string) => api.post<Client>('/clients', { full_name: fullName, phone }),
};

export const vehiclesApi = {
  get: (id: string) => api.get<Vehicle>(`/vehicles/${id}`),
  owner: (id: string) => api.get<Client | null>(`/vehicles/${id}/owner`),
  workHistory: (id: string, category: WorkCategory[] = []) =>
    api.get<WorkHistory>(`/vehicles/${id}/work-history${buildQuery({ category })}`),
  create: (body: VehicleCreate) => api.post<Vehicle>('/vehicles', body),
  attachOwner: (vehicleId: string, clientId: string) =>
    api.post<{ id: string }>(`/vehicles/${vehicleId}/owners`, {
      client_id: clientId,
      date_from: new Date().toISOString().slice(0, 10),
    }),
};

export const searchApi = {
  search: (query: string) => api.get<SearchHit[]>(`/search?q=${q(query)}`),
  recent: () => api.get<RecentView[]>('/search/recent'),
};

export const usersApi = {
  mechanics: () => api.get<User[]>('/users/mechanics'),
  masters: () => api.get<User[]>('/users/masters'),
  create: (body: UserCreate) => api.post<User>('/users', body),
};

export const catalogApi = {
  suggest: (text: string) => api.get<CatalogItem[]>(`/catalog/suggest?text=${q(text)}`),
};

export const consentApi = {
  paper: (fullName: string, phone: string) =>
    api.post<{ client_id: string }>('/consent/paper', { full_name: fullName, phone }),
};

export const statsApi = {
  section: (section: StatsSection, period: StatsPeriod, masterId?: string) =>
    api.get<Stats>(`/stats/${section}${buildQuery({ period, master_id: masterId })}`),
  mine: (period: StatsPeriod) => api.get<Stats>(`/stats/mine${buildQuery({ period })}`),
};

export const settingsApi = {
  get: () => api.get<VisibilitySettings>('/settings'),
  update: (body: Partial<VisibilitySettings>) => api.patch<VisibilitySettings>('/settings', body),
  pay: () => api.get<MechanicPay[]>('/settings/pay'),
  setPay: (userId: string, scheme: PayScheme | null, value: number | null) =>
    api.patch<MechanicPay>(`/settings/pay/${userId}`, { pay_scheme: scheme, pay_value: value }),
};
