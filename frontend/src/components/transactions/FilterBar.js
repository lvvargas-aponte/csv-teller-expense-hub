import React from 'react';

export default function FilterBar({
  banks,
  months,
  bank,
  month,
  split,
  search,
  onBankChange,
  onMonthChange,
  onSplitChange,
  onSearchChange,
  visibleCount,
  totalCount,
}) {
  const bankActive  = bank  !== 'all';
  const monthActive = month !== 'all';
  const splitActive = split !== 'all';

  return (
    <div className="tx-filter-bar">
      <span className="tx-filter-label">Filter</span>

      <div className="tx-sel-wrap">
        <select
          className={bankActive ? 'tx-sel--active' : ''}
          value={bank}
          onChange={(e) => onBankChange(e.target.value)}
          aria-label="Filter by bank"
        >
          <option value="all">All banks</option>
          {banks.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      <div className="tx-sel-wrap">
        <select
          className={monthActive ? 'tx-sel--active' : ''}
          value={month}
          onChange={(e) => onMonthChange(e.target.value)}
          aria-label="Filter by month"
        >
          <option value="all">All months</option>
          {months.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </select>
      </div>

      <div className="tx-sel-wrap">
        <select
          className={splitActive ? 'tx-sel--active' : ''}
          value={split}
          onChange={(e) => onSplitChange(e.target.value)}
          aria-label="Filter by type"
        >
          <option value="all">All</option>
          <option value="personal">Personal</option>
          <option value="shared">Shared</option>
        </select>
      </div>

      <div className="tx-search-wrap">
        <span className="tx-search-icon" aria-hidden="true">⌕</span>
        <input
          type="text"
          placeholder="Search transactions…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label="Search transactions"
        />
      </div>

      <div className="tx-filter-spacer" />
      <span className="tx-filter-count">
        {visibleCount !== totalCount
          ? `${visibleCount} of ${totalCount}`
          : `${totalCount} transactions`}
      </span>
    </div>
  );
}
