import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { useCallback, useRef } from 'react';
import { telegram } from '../telegram/webapp';
import { useToast } from '../ui/Toast';

/**
 * One-tap actions (status, approve, assign): the button shows busy, failures go to a toast.
 * `mutate` is ref-locked: a double tap lands before React re-renders the button as disabled.
 */
export function useAction<TVars = void, TData = unknown>(
  fn: (vars: TVars) => Promise<TData>,
  opts: { invalidate?: QueryKey[]; onSuccess?: (data: TData) => void } = {},
) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const inFlight = useRef(false);
  const mutation = useMutation<TData, Error, TVars>({
    mutationFn: fn,
    onSuccess: async (data) => {
      telegram.haptic('success');
      await Promise.all((opts.invalidate ?? []).map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      opts.onSuccess?.(data);
    },
    onError: (error) => {
      telegram.haptic('error');
      toast.show(error.message);
    },
    onSettled: () => {
      inFlight.current = false;
    },
  });
  const { mutate: rawMutate } = mutation;
  const mutate = useCallback(
    (vars?: TVars) => {
      if (inFlight.current) return;
      inFlight.current = true;
      rawMutate(vars as TVars);
    },
    [rawMutate],
  );
  return { ...mutation, mutate };
}
