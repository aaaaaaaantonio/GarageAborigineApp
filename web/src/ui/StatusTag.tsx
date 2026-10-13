import type { VisitStatus, WorkItemStatus } from '../api/types';
import { VISIT_STATUS_LABELS, WORK_STATUS_LABELS } from '../lib/labels';

const VISIT_TONE: Record<VisitStatus, string> = {
  received: 'neutral', diagnostics: 'neutral', approval: 'approval', in_progress: 'repair',
  waiting_parts: 'parts', ready: 'ready', issued: 'issued', cancelled: 'cancelled',
};
const WORK_TONE: Record<WorkItemStatus, string> = {
  not_ready: 'neutral', in_progress: 'repair', waiting_parts: 'parts', ready: 'ready',
};

type Props = { kind: 'visit'; status: VisitStatus } | { kind: 'work'; status: WorkItemStatus };

export function StatusTag(props: Props) {
  const [tone, label] =
    props.kind === 'visit'
      ? [VISIT_TONE[props.status], VISIT_STATUS_LABELS[props.status]]
      : [WORK_TONE[props.status], WORK_STATUS_LABELS[props.status]];
  // A finished visit reads at a glance even without colour.
  const mark = props.kind === 'visit' && props.status === 'issued' ? '✓ ' : '';
  return <span className={`tag tag-${tone}`}>{mark}{label}</span>;
}
