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
  allowed_next_statuses: VisitStatus[];
}

export interface VisitList {
  items: Visit[];
  has_more: boolean;
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
