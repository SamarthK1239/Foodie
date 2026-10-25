import { useSetFavorite } from '../api/hooks'

export function FavoriteStar({
  id,
  isFavorite,
  className = '',
}: {
  id: number
  isFavorite: boolean
  className?: string
}) {
  const setFavorite = useSetFavorite()

  return (
    <button
      type="button"
      aria-label={isFavorite ? 'Remove from favourites' : 'Add to favourites'}
      aria-pressed={isFavorite}
      title={isFavorite ? 'Remove from favourites' : 'Add to favourites'}
      disabled={setFavorite.isPending}
      onClick={(event) => {
        // Stars usually sit inside a card-wide link; a tap here means "star
        // this", not "open this".
        event.preventDefault()
        event.stopPropagation()
        setFavorite.mutate({ id, isFavorite: !isFavorite })
      }}
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-lg transition disabled:opacity-40 ${
        isFavorite ? 'text-amber-300 hover:text-amber-200' : 'text-white/25 hover:text-white/60'
      } ${className}`}
    >
      {isFavorite ? '★' : '☆'}
    </button>
  )
}
