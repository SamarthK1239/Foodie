import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from './client'
import type {
  AdminStats,
  AnalyticsSummary,
  CookEvent,
  CookResult,
  ExpiryScan,
  GroceryItem,
  GroceryStatus,
  IngestStatusResponse,
  Ingredient,
  MealPlanEntry,
  MealPlanWeek,
  PeriodReview,
  InventoryItem,
  InventorySummary,
  Recipe,
  RecipeList,
  ScanProduct,
  Suggestion,
  UnmatchedLine,
} from './types'

// Anything that can change when stock moves; refreshed together after a mutation.
const STOCK_DEPENDENT = ['inventory', 'inventory-summary', 'suggestions', 'grocery', 'analytics']

function useInvalidate() {
  const queryClient = useQueryClient()
  return (keys: string[] = STOCK_DEPENDENT) => {
    for (const key of keys) queryClient.invalidateQueries({ queryKey: [key] })
  }
}

// --- Inventory -------------------------------------------------------------------

export function useInventory(params: { status?: string; search?: string; bucket?: string } = {}) {
  return useQuery({
    queryKey: ['inventory', params],
    queryFn: () => api.get<InventoryItem[]>(`/api/inventory/items${qs(params)}`),
  })
}

export function useInventorySummary() {
  return useQuery({
    queryKey: ['inventory-summary'],
    queryFn: () => api.get<InventorySummary>('/api/inventory/summary'),
  })
}

export function useExpiring(withinDays = 5) {
  return useQuery({
    queryKey: ['inventory', 'expiring', withinDays],
    queryFn: () => api.get<InventoryItem[]>(`/api/inventory/expiring${qs({ within_days: withinDays })}`),
  })
}

export interface NewItem {
  ingredient_name: string
  quantity: number
  unit: string
  expiry_date?: string
  purchase_date?: string
  location?: string
  cost?: number
  notes?: string
}

export function useAddItem() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (item: NewItem) => api.post<InventoryItem>('/api/inventory/items', item),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateItem() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number } & Partial<InventoryItem>) =>
      api.patch<InventoryItem>(`/api/inventory/items/${id}`, patch),
    onSuccess: () => invalidate(),
  })
}

export function useAdjustItem() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, delta, reason }: { id: number; delta: number; reason?: string }) =>
      api.post<InventoryItem>(`/api/inventory/items/${id}/adjust`, { delta, reason: reason ?? 'manual_adjust' }),
    onSuccess: () => invalidate(),
  })
}

export function useItemAction(action: 'discard' | 'finish') {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: number) => api.post<InventoryItem>(`/api/inventory/items/${id}/${action}`),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteItem() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/inventory/items/${id}`),
    onSuccess: () => invalidate(),
  })
}

export function useIngredients(search = '') {
  return useQuery({
    queryKey: ['ingredients', search],
    queryFn: () => api.get<Ingredient[]>(`/api/ingredients${qs({ search })}`),
  })
}

export function useUpdateIngredient() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number } & Partial<Ingredient>) =>
      api.patch<Ingredient>(`/api/ingredients/${id}`, patch),
    onSuccess: () => invalidate(['ingredients', ...STOCK_DEPENDENT]),
  })
}

// --- Recipes ---------------------------------------------------------------------

export function useRecipes(
  params: {
    search?: string
    limit?: number
    offset?: number
    favorites_only?: boolean
    sort?: 'title' | 'favorite'
  } = {},
) {
  return useQuery({
    queryKey: ['recipes', params],
    queryFn: () => api.get<RecipeList>(`/api/recipes${qs(params)}`),
  })
}

export function useRecipe(id: number | undefined) {
  return useQuery({
    queryKey: ['recipe', id],
    queryFn: () => api.get<Recipe>(`/api/recipes/${id}`),
    enabled: id !== undefined,
  })
}

export interface RecipeInput {
  title: string
  instructions: string
  servings?: number | null
  total_minutes?: number | null
  tags: string[]
  ingredients: { raw_text: string; optional: boolean }[]
}

export function useSaveRecipe(id?: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (recipe: RecipeInput) =>
      id === undefined
        ? api.post<Recipe>('/api/recipes', recipe)
        : api.patch<Recipe>(`/api/recipes/${id}`, recipe),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      queryClient.invalidateQueries({ queryKey: ['recipe', saved.id] })
      queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    },
  })
}

export function useDeleteRecipe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/recipes/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    },
  })
}

export function useSetFavorite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, isFavorite }: { id: number; isFavorite: boolean }) =>
      api.post<Recipe>(`/api/recipes/${id}/favorite`, { is_favorite: isFavorite }),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      queryClient.invalidateQueries({ queryKey: ['recipe', saved.id] })
    },
  })
}

// --- Meal plan -------------------------------------------------------------------

// Planning changes what you need to buy, so the grocery list moves with it.
const PLAN_DEPENDENT = ['meal-plan', 'grocery']

export function useMealPlanWeek(weekStart?: string) {
  const params = weekStart ? { week_start: weekStart } : {}
  return useQuery({
    queryKey: ['meal-plan', params],
    queryFn: () => api.get<MealPlanWeek>(`/api/meal-plan${qs(params)}`),
  })
}

export function useAddToWeek() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: {
      recipe_id: number
      week_start?: string
      servings_multiplier?: number
      note?: string
    }) => api.post<MealPlanEntry>('/api/meal-plan', body),
    onSuccess: () => invalidate(PLAN_DEPENDENT),
  })
}

export function useRemoveFromWeek() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/meal-plan/${id}`),
    onSuccess: () => invalidate(PLAN_DEPENDENT),
  })
}

// --- Suggestions & cooking -------------------------------------------------------
export function useSuggestions(params: { limit?: number; offset?: number; min_coverage?: number } = {}) {
  return useQuery({
    queryKey: ['suggestions', params],
    queryFn: () => api.get<Suggestion[]>(`/api/suggestions${qs(params)}`),
  })
}

export function useCook() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, multiplier }: { id: number; multiplier?: number }) =>
      api.post<CookResult>(`/api/recipes/${id}/cook`, { servings_multiplier: multiplier ?? 1 }),
    onSuccess: () => invalidate([...STOCK_DEPENDENT, 'cook-events']),
  })
}

export function useCookEvents() {
  return useQuery({
    queryKey: ['cook-events'],
    queryFn: () => api.get<CookEvent[]>('/api/cook-events'),
  })
}

export function useSetLeftoverState() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, state }: { id: number; state: 'in_fridge' | 'finished' }) =>
      api.patch<CookEvent>(`/api/cook-events/${id}`, { leftover_state: state }),
    onSuccess: () => invalidate(['cook-events']),
  })
}

// --- Grocery ---------------------------------------------------------------------

export function useGrocery(status: GroceryStatus = 'pending') {
  return useQuery({
    queryKey: ['grocery', status],
    queryFn: () => api.get<GroceryItem[]>(`/api/grocery${qs({ status })}`),
  })
}

export function useAddGrocery() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (item: { ingredient_name: string; quantity?: number; unit?: string }) =>
      api.post<GroceryItem>('/api/grocery', item),
    onSuccess: () => invalidate(['grocery']),
  })
}

export function useUpdateGrocery() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number } & Partial<GroceryItem>) =>
      api.patch<GroceryItem>(`/api/grocery/${id}`, patch),
    onSuccess: () => invalidate(['grocery']),
  })
}

export function useDeleteGrocery() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/grocery/${id}`),
    onSuccess: () => invalidate(['grocery']),
  })
}

export function useClearPurchased() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: () => api.post<void>('/api/grocery/clear-purchased'),
    onSuccess: () => invalidate(['grocery']),
  })
}

// --- Analytics & admin -----------------------------------------------------------

export function useAnalyticsSummary(days = 30) {
  return useQuery({
    queryKey: ['analytics', 'summary', days],
    queryFn: () => api.get<AnalyticsSummary>(`/api/analytics/summary${qs({ days })}`),
  })
}

export function useAnalyticsSeries<T>(endpoint: string, days: number) {
  return useQuery({
    queryKey: ['analytics', endpoint, days],
    queryFn: () => api.get<T[]>(`/api/analytics/${endpoint}${qs({ days })}`),
  })
}

export function useAdminStats() {
  return useQuery({ queryKey: ['admin-stats'], queryFn: () => api.get<AdminStats>('/api/admin/stats') })
}

export function useIngestStatus(poll: boolean) {
  return useQuery({
    queryKey: ['ingest-status'],
    queryFn: () => api.get<IngestStatusResponse>('/api/admin/ingest/status'),
    refetchInterval: poll ? 3000 : false,
  })
}

export function useStartIngest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { mode: string; max_recipes?: number; sites?: string[] }) =>
      api.post('/api/admin/ingest/start', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ingest-status'] }),
  })
}

export function useCancelIngest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/admin/ingest/cancel'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ingest-status'] }),
  })
}

export function useUnmatched() {
  return useQuery({
    queryKey: ['unmatched'],
    queryFn: () => api.get<UnmatchedLine[]>('/api/admin/unmatched-ingredients'),
  })
}

export function useResolveUnmatched() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { recipe_ingredient_id: number; ingredient_name: string }) =>
      api.post('/api/admin/unmatched-ingredients/resolve', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['unmatched'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    },
  })
}

// --- Two-week review -------------------------------------------------------------

export function usePeriodReview(weeks: number) {
  return useQuery({
    queryKey: ['analytics', 'period-review', weeks],
    queryFn: () => api.get<PeriodReview>(`/api/analytics/period-review${qs({ weeks })}`),
  })
}

export function useApplyPeriodReview() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (ingredientIds: number[]) =>
      api.post<{ added: number; grocery_item_ids: number[] }>(
        '/api/analytics/period-review/apply',
        { ingredient_ids: ingredientIds },
      ),
    onSuccess: () => invalidate(['grocery', 'analytics']),
  })
}

// --- Barcode scanning ------------------------------------------------------------

export function useLookupBarcode() {
  return useMutation({
    mutationFn: (barcode: string) =>
      api.get<ScanProduct>(`/api/scan/barcode/${encodeURIComponent(barcode)}`),
  })
}

export function useScanToInventory() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: NewItem & { barcode: string }) =>
      api.post<InventoryItem>('/api/scan/to-inventory', body),
    onSuccess: () => invalidate(),
  })
}

export function useScanExpiry() {
  return useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData()
      body.append('image', file)
      // FormData must set its own multipart boundary, so this one bypasses the
      // JSON client rather than fighting its Content-Type header.
      const response = await fetch('/api/scan/expiry', { method: 'POST', body })
      if (!response.ok) throw new Error('Could not read that photo')
      return (await response.json()) as ExpiryScan
    },
  })
}
