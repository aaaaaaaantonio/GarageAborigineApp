export type Role = 'admin' | 'master' | 'mechanic';
export type VisitStatus =
  | 'received' | 'diagnostics' | 'approval' | 'in_progress'
  | 'waiting_parts' | 'ready' | 'issued' | 'cancelled';
export type WorkItemStatus = 'not_ready' | 'in_progress' | 'waiting_parts' | 'ready';
export type WorkCategory = 'diagnostics' | 'maintenance' | 'body' | 'electrical' | 'chassis' | 'other';

export interface User {
  id: string;
  role: Role;
  full_name: string;
  telegram_id: number | null;
  phone: string | null;
  branch_id: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface Visit {
  id: string;
  status: VisitStatus;
  mileage_at_intake: number;
  total_amount: number;
  created_at: string;
  client_id: string;
  client_name: string;
  vehicle_id: string;
  plate_number: string;
  make_model: string;
  assigned_master_id: string;
  master_name: string;
  status_changed_at: string;
  last_activity_at: string;
  allowed_next_statuses: VisitStatus[];
}

export interface VisitList {
  items: Visit[];
  has_more: boolean;
  /** Over the whole filter, not just this page. */
  total_count: number;
  issued_amount: number;
}

export type VisitSort = 'date' | 'stale' | 'status' | 'amount';

export interface VisitListParams {
  active?: boolean;
  closed?: boolean;
  status?: VisitStatus[];
  client_id?: string;
  vehicle_id?: string;
  master_id?: string;
  unassigned_work?: boolean;
  stale?: boolean;
  since?: string;
  sort?: VisitSort;
  offset?: number;
}

export interface VisitCreate {
  client_id: string;
  vehicle_id: string;
  assigned_master_id: string;
  mileage_at_intake: number;
  mileage_manually_confirmed: boolean;
}

export interface WorkItem {
  id: string;
  visit_id: string;
  name: string;
  status: WorkItemStatus;
  approved_by_client: boolean;
  free_text_name: string | null;
  catalog_item_id: string | null;
  assigned_mechanic_id: string | null;
  assigned_mechanic_name: string | null;
  allowed_next_statuses: WorkItemStatus[];
}

export interface MyWorkItem {
  id: string;
  visit_id: string;
  name: string;
  status: WorkItemStatus;
  free_text_name: string | null;
  catalog_item_id: string | null;
  plate_number: string | null;
  make_model: string | null;
  allowed_next_statuses: WorkItemStatus[];
}

/** A finished work item in a closed visit — read-only history for the mechanic. */
export interface DoneWorkItem {
  id: string;
  visit_id: string;
  name: string;
  plate_number: string | null;
  make_model: string | null;
  visit_status: Extract<VisitStatus, 'issued' | 'cancelled'>;
  visit_date: string;
  closed_at: string;
  norm_hours: number;
}

export interface DoneWorkList {
  items: DoneWorkItem[];
  count: number;
  total_norm_hours: number;
  has_more: boolean;
}

export type MineSort = 'urgency' | 'car';
export type BoardGroup = 'mechanic' | 'status' | 'car';

export interface BoardItem {
  id: string;
  visit_id: string;
  name: string;
  status: WorkItemStatus;
  category: WorkCategory;
  approved_by_client: boolean;
  norm_hours: number;
  assigned_mechanic_id: string | null;
  assigned_mechanic_name: string | null;
  plate_number: string | null;
  make_model: string | null;
  visit_status: VisitStatus;
}

export interface BoardList {
  items: BoardItem[];
  has_more: boolean;
}

export interface BoardParams {
  mechanic_id?: string;
  unassigned?: boolean;
  status?: WorkItemStatus[];
  category?: WorkCategory[];
  unapproved?: boolean;
  group?: BoardGroup;
}

export interface WorkItemCreate {
  catalog_item_id: string | null;
  free_text_name: string | null;
  category: WorkCategory;
  norm_hours: number;
  hourly_rate: number;
  assigned_mechanic_id: string | null;
}

export interface PartItemCreate {
  work_item_id: string;
  name: string;
  quantity: number;
  unit_price: number;
}

export interface PartItem {
  id: string;
  name: string;
  quantity: number;
  unit_price: number;
}

export interface PartLine {
  id: string;
  work_item_id: string;
  name: string;
  quantity: number;
  unit_price: number;
  amount: number;
}

export interface WorkLine {
  id: string;
  name: string;
  status: WorkItemStatus;
  assigned_mechanic_name: string | null;
  approved_by_client: boolean;
  norm_hours: number;
  hourly_rate: number;
  amount: number;
  parts: PartLine[];
}

/** GET /visits/{id}/lines — staff only. */
export interface VisitLines {
  works: WorkLine[];
  works_total: number;
  parts_total: number;
  discount: number;
  total: number;
}

export interface Client {
  id: string;
  full_name: string;
  phone_display: string;
  client_type: 'individual' | 'legal';
}

export interface Vehicle {
  id: string;
  vin: string;
  plate_number: string;
  make: string;
  model: string;
  mileage_current: number;
}

export interface VehicleCreate {
  vin: string;
  plate_number: string;
  make: string;
  model: string;
}

export interface WorkHistoryItem {
  visit_id: string;
  visit_at: string;
  mileage: number;
  name: string;
  status: WorkItemStatus;
  category: WorkCategory;
}

export interface WorkHistory {
  items: WorkHistoryItem[];
  has_more: boolean;
}

export interface CatalogItem {
  id: string;
  name: string;
  category: WorkCategory;
  default_norm_hours: number;
}

export interface SearchHit {
  entity: 'client' | 'vehicle';
  id: string;
  matched_field: string;
}

export interface RecentView {
  entity_type: 'client' | 'vehicle';
  entity_id: string;
}

export interface UserCreate {
  role: Role;
  full_name: string;
  telegram_id: number | null;
}

export type StatsPeriod = 'week' | 'month' | 'quarter' | 'year';
export type StatsSection = 'money' | 'flow' | 'staff' | 'works';
export type StatsUnit = 'rub' | 'count' | 'hours' | 'days' | 'pct' | 'text';

export interface StatsKpi {
  key: string;
  label: string;
  value: number | string;
  unit: StatsUnit;
  delta_pct: number | null;
  compare: boolean;
  higher_is_better?: boolean;
}

export interface StatsChartData {
  key: string;
  kind: 'bars' | 'stack' | 'hbars' | 'share';
  title: string;
  sub: string | null;
  unit: StatsUnit;
  labels: string[];
  series: { name: string; values: number[] }[];
}

export interface Stats {
  section: string;
  period: StatsPeriod;
  kpis: StatsKpi[];
  charts: StatsChartData[];
}

export type PayScheme = 'percent' | 'per_hour' | 'full';

export interface VisibilitySettings {
  mechanic_sees_prices: boolean;
  mechanic_sees_client_name: boolean;
  mechanic_sees_client_phone: boolean;
  mechanic_sees_vin: boolean;
}

export interface MechanicPay {
  user_id: string;
  full_name: string;
  pay_scheme: PayScheme | null;
  pay_value: number | null;
}

export interface MechanicPart {
  name: string;
  article_number: string | null;
  quantity: number;
  availability_status: string;
  unit_price: number | null;
  amount: number | null;
}

export interface MechanicWork {
  id: string;
  name: string;
  category: WorkCategory;
  status: WorkItemStatus;
  mechanic_name: string | null;
  is_mine: boolean;
  norm_hours: number;
  hourly_rate: number | null;
  amount: number | null;
  my_pay: number | null;
  parts: MechanicPart[];
}

/** The visit card for a mechanic: fields the admin's settings hide are null. */
export interface MechanicVisit {
  id: string;
  status: VisitStatus;
  created_at: string;
  mileage_at_intake: number;
  plate_number: string;
  make_model: string;
  master_name: string;
  client_name: string | null;
  client_phone: string | null;
  client_telegram_username: string | null;
  vin: string | null;
  discount: number | null;
  total_amount: number | null;
  my_pay_total: number | null;
  works: MechanicWork[];
}
