import { http, HttpResponse } from 'msw';
import type { Client, MyWorkItem, Vehicle, Visit, WorkItem, WorkLine } from '../api/types';
import { server } from './server';

export function makeVisit(over: Partial<Visit> = {}): Visit {
  return {
    id: 'v1', status: 'in_progress', mileage_at_intake: 120500, total_amount: 9850,
    created_at: '2026-10-10T09:00:00Z', client_id: 'c1', client_name: 'Петров Иван',
    vehicle_id: 'veh1', plate_number: 'А123ВС77', make_model: 'Toyota Camry',
    assigned_master_id: 'u-master', master_name: 'Орлов Пётр',
    allowed_next_statuses: ['waiting_parts', 'ready', 'cancelled'], ...over,
  };
}

export function makeWorkItem(over: Partial<WorkItem> = {}): WorkItem {
  return {
    id: 'w1', visit_id: 'v1', name: 'Замена масла ДВС', status: 'in_progress', approved_by_client: false,
    free_text_name: null, catalog_item_id: 'cat1', assigned_mechanic_id: 'u-mech',
    assigned_mechanic_name: 'Сидоров Иван', allowed_next_statuses: ['waiting_parts', 'ready'], ...over,
  };
}

export function makeMyWork(over: Partial<MyWorkItem> = {}): MyWorkItem {
  return {
    id: 'w1', visit_id: 'v1', name: 'Замена масла ДВС', status: 'not_ready', free_text_name: null,
    catalog_item_id: 'cat1', plate_number: 'А123ВС77', make_model: 'Toyota Camry',
    allowed_next_statuses: ['in_progress'], ...over,
  };
}

export const CLIENT: Client = { id: 'c1', full_name: 'Петров Иван', phone_display: '+7 900 123-45-67', client_type: 'individual' };
export const VEHICLE: Vehicle = {
  id: 'veh1', vin: 'JTDBR32E720012345', plate_number: 'А123ВС77', make: 'Toyota', model: 'Camry', mileage_current: 120500,
};

export function makeWorkLine(over: Partial<WorkLine> = {}): WorkLine {
  return {
    id: 'w1', name: 'Замена масла ДВС', status: 'in_progress', assigned_mechanic_name: 'Сидоров Иван',
    approved_by_client: false, norm_hours: 0.5, hourly_rate: 2400, amount: 1200,
    parts: [{ id: 'p1', work_item_id: 'w1', name: 'Фильтр', quantity: 1, unit_price: 450, amount: 450 }],
    ...over,
  };
}

export function mockVisitPage(visit: Visit = makeVisit(), works: WorkLine[] = [makeWorkLine()]) {
  const worksTotal = works.reduce((sum, w) => sum + w.amount, 0);
  const partsTotal = works.reduce((sum, w) => sum + w.parts.reduce((s, p) => s + p.amount, 0), 0);
  server.use(
    http.get(`/api/visits/${visit.id}`, () => HttpResponse.json(visit)),
    http.get(`/api/visits/${visit.id}/lines`, () =>
      HttpResponse.json({ works, works_total: worksTotal, parts_total: partsTotal, discount: 0, total: worksTotal + partsTotal })),
  );
}
