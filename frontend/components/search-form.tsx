interface SearchFormProps {
  defaultValue: string;
  mode: 'classic' | 'smart';
  label: string;
  placeholder: string;
}

export function SearchForm({ defaultValue, mode, label, placeholder }: SearchFormProps) {
  return (
    <form action="/search" className="search-form card">
      <input type="hidden" name="mode" value={mode} />
      <label className="search-form__label">
        <span>{label}</span>
        {mode === 'classic' ? (
          <input name="q" defaultValue={defaultValue} placeholder={placeholder} className="search-input" />
        ) : (
          <textarea name="q" defaultValue={defaultValue} placeholder={placeholder} className="search-textarea" rows={4} />
        )}
      </label>
      <button type="submit" className="button button-primary">
        Run {mode} search
      </button>
    </form>
  );
}
