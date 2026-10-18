import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchApi, settingsApi } from '../api/endpoints';
import { useAuth } from '../auth/AuthProvider';
import { useDebounced } from '../lib/useDebounced';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { ScreenHeader } from '../ui/ScreenHeader';
import { HitList } from './hits';

export function SearchScreen() {
  const { user } = useAuth();
  const isMechanic = user!.role === 'mechanic';
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get('q') ?? '');
  const query = useDebounced(text.trim(), 300);
  useEffect(() => {
    setParams(query ? { q: query } : {}, { replace: true });
  }, [query, setParams]);
  const active = query.length >= 2;
  const results = useQuery({ queryKey: ['search', query], queryFn: () => searchApi.search(query), enabled: active });
  const recent = useQuery({ queryKey: ['recent'], queryFn: searchApi.recent, enabled: !active });
  // Mechanics can't find a car by VIN while the admin hides VINs from them.
  const visibility = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get, enabled: isMechanic });
  const prompt = !isMechanic
    ? 'Госномер, VIN, телефон или ФИО'
    : visibility.data?.mechanic_sees_vin === false
      ? 'Госномер'
      : 'Госномер или VIN';
  return (
    <>
      <ScreenHeader title="Поиск" />
      <div className="field search-field">
        <input type="search" aria-label="Поиск" placeholder={prompt} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
      </div>
      {active ? (
        <Loadable query={results}>
          {(hits) => (hits.length ? <HitList hits={hits} /> : <EmptyState text="Ничего не найдено" />)}
        </Loadable>
      ) : (
        <Loadable query={recent}>
          {(views) => {
            const hits = views
              .map((v) => ({ entity: v.entity_type, id: v.entity_id }))
              .filter((h) => !isMechanic || h.entity === 'vehicle');
            if (hits.length === 0) return <EmptyState text={`Введите ${prompt.charAt(0).toLowerCase()}${prompt.slice(1)}`} />;
            return (
              <>
                <h2 className="section-title">Недавние</h2>
                <HitList hits={hits} />
              </>
            );
          }}
        </Loadable>
      )}
    </>
  );
}
