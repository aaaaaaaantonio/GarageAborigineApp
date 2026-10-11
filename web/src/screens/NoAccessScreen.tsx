import { ScreenHeader } from '../ui/ScreenHeader';
import { EmptyState } from '../ui/EmptyState';

export function NoAccessScreen() {
  return (
    <>
      <ScreenHeader title="Нет доступа" back />
      <EmptyState text="Нет доступа к этому разделу" />
    </>
  );
}
