import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  importDocumentFromUrl,
  getAllowedHosts,
  listDocuments,
} from '../../../api/documents';
import {
  listSeeds, addSeed, deleteSeed, listHiddenSeeds, restoreDefault,
} from '../../../api/seeds';

/**
 * Suggested seed material — populated at runtime from /api/seeds.
 *
 * Defaults ship in backend/data/seeds_default.json; user additions and
 * removals overlay via the seeds DB tables.  Each seed row carries
 * is_custom so the UI knows whether deletion is "remove forever" or
 * "hide default" (both call DELETE /api/seeds/{id}).
 */
export default function SuggestedSeeds({ onImported }) {
  const [seedGroups, setSeedGroups] = useState([]);
  const [seedsLoadError, setSeedsLoadError] = useState(null);

  const [allowed, setAllowed] = useState(null);
  const [allowedError, setAllowedError] = useState(null);

  const [busy, setBusy] = useState({});      // {url: 'pending'|'done'|'error'}
  const [errors, setErrors] = useState({});  // {url: message}
  const [notices, setNotices] = useState({});
  const [importedSet, setImportedSet] = useState(new Set());
  const [refreshState, setRefreshState] = useState(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const [hidden, setHidden] = useState([]);
  const [showHidden, setShowHidden] = useState(false);

  const reloadSeeds = useCallback(() => {
    listSeeds()
      .then((r) => {
        setSeedGroups(r.data || []);
        setSeedsLoadError(null);
      })
      .catch((e) => {
        setSeedsLoadError(
          e?.response?.data?.detail || e.message || 'Could not load seeds.',
        );
      });
    listHiddenSeeds()
      .then((r) => setHidden(r.data || []))
      .catch(() => setHidden([]));
  }, []);

  const reloadAllowed = useCallback(() => {
    getAllowedHosts()
      .then((r) => setAllowed(new Set(r.data || [])))
      .catch((e) => {
        setAllowed(new Set());
        setAllowedError(
          e?.response?.status === 404
            ? 'Backend does not expose /api/documents/allowed-hosts yet — restart the backend to load the new routes.'
            : (e?.response?.data?.detail || e.message || 'Could not reach backend.'),
        );
      });
  }, []);

  useEffect(() => {
    reloadSeeds();
    reloadAllowed();
  }, [reloadSeeds, reloadAllowed]);

  const refreshImportedSet = useCallback(async () => {
    try {
      const r = await listDocuments();
      // A doc is "the same imported thing" if either its source URL OR
      // the URL it was originally fetched from matches the seed URL.
      // Older rows store the post-redirect URL in `source`; newer rows
      // store the user-requested URL there.  Index both so the green
      // pill renders regardless of when the row was created.
      const urls = new Set();
      for (const d of (r.data || [])) {
        if (d.status === 'superseded') continue;
        if (d.source) urls.add(d.source);
        if (d.metadata?.fetched_url) urls.add(d.metadata.fetched_url);
        if (d.metadata?.requested_url) urls.add(d.metadata.requested_url);
      }
      setImportedSet(urls);
    } catch {
      setImportedSet(new Set());
    }
  }, []);

  useEffect(() => {
    refreshImportedSet();
  }, [refreshImportedSet]);

  const importableReason = (urlStr) => {
    if (allowed === null) return 'Loading allowlist…';
    try {
      const host = new URL(urlStr).host;
      if (allowed.has(host)) return null;
      return `Host ${host} is not on the backend allowlist.`;
    } catch {
      return 'Invalid URL.';
    }
  };

  const importSeed = async (seed) => {
    setBusy((b) => ({ ...b, [seed.url]: 'pending' }));
    setErrors((e) => ({ ...e, [seed.url]: null }));
    setNotices((n) => ({ ...n, [seed.url]: null }));
    try {
      const r = await importDocumentFromUrl({
        url: seed.url,
        scope: seed.scope,
        category: seed.category,
        title: seed.title,
      });
      const body = r.data || {};
      let outcome = 'imported';
      if (body.duplicate) outcome = 'duplicate';
      else if (body.replaces_id) outcome = 'replaced';
      setBusy((b) => ({ ...b, [seed.url]: 'done' }));
      setNotices((n) => ({
        ...n,
        [seed.url]: outcome === 'replaced'
          ? `Replaces previous version (#${body.replaces_id} from ${body.replaces_uploaded_at?.slice(0, 10) || 'earlier'}).`
          : outcome === 'duplicate'
          ? 'Already in the corpus — no change since last import.'
          : 'Imported.',
      }));
      if (onImported) onImported();
      refreshImportedSet();
      return outcome;
    } catch (err) {
      setBusy((b) => ({ ...b, [seed.url]: 'error' }));
      setErrors((e) => ({
        ...e,
        [seed.url]: err?.response?.data?.detail || err.message,
      }));
      return 'failed';
    }
  };

  const removeSeed = async (seed) => {
    const verb = seed.is_custom ? 'remove' : 'hide';
    if (!window.confirm(`${verb === 'remove' ? 'Remove' : 'Hide'} "${seed.title}" from the seed list?`)) {
      return;
    }
    try {
      await deleteSeed(seed.id);
      reloadSeeds();
    } catch (err) {
      window.alert(err?.response?.data?.detail || err.message || 'Delete failed.');
    }
  };

  const flatSeeds = useMemo(
    () => seedGroups.flatMap((g) => g.seeds),
    [seedGroups],
  );

  const refreshable = useMemo(() => {
    return flatSeeds.filter(
      (s) => importableReason(s.url) === null && importedSet.has(s.url),
    );
  }, [flatSeeds, importedSet, allowed]);  // eslint-disable-line react-hooks/exhaustive-deps

  const refreshAll = async () => {
    if (!refreshable.length) return;
    const summary = { unchanged: 0, replaced: [], failed: [] };
    setRefreshState({ total: refreshable.length, done: 0, summary });
    for (let i = 0; i < refreshable.length; i++) {
      const seed = refreshable[i];
      const outcome = await importSeed(seed);
      if (outcome === 'duplicate') summary.unchanged += 1;
      else if (outcome === 'replaced') summary.replaced.push(seed.title);
      else if (outcome === 'failed') summary.failed.push(seed.title);
      setRefreshState({
        total: refreshable.length,
        done: i + 1,
        summary: { ...summary },
      });
    }
  };

  const addCustomSeed = async (payload) => {
    setAddError(null);
    try {
      await addSeed(payload);
      reloadSeeds();
      reloadAllowed();   // host was auto-allowlisted; refresh local set
      setAdding(false);
    } catch (err) {
      setAddError(err?.response?.data?.detail || err.message || 'Add failed.');
    }
  };

  const restoreSeed = async (seed) => {
    try {
      await restoreDefault(seed.id);
      reloadSeeds();
    } catch (err) {
      window.alert(err?.response?.data?.detail || err.message || 'Restore failed.');
    }
  };

  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 8, padding: 16,
      background: 'var(--bg-root)', color: 'var(--text-primary)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
        <div style={{ fontWeight: 600, flex: 1 }}>
          Suggested seed material
        </div>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            borderRadius: 6, padding: '4px 10px', fontSize: 12, cursor: 'pointer',
          }}>
          {adding ? 'Cancel' : '+ Add seed'}
        </button>
        <button
          type="button"
          onClick={refreshAll}
          disabled={!refreshable.length || (refreshState && refreshState.done < refreshState.total)}
          title={
            !refreshable.length
              ? 'Import at least one seed before refreshing.'
              : `Re-fetches ${refreshable.length} previously-imported seed${refreshable.length === 1 ? '' : 's'}; new versions are linked to old ones.`
          }
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '4px 10px', fontSize: 12,
            cursor: refreshable.length && !(refreshState && refreshState.done < refreshState.total) ? 'pointer' : 'not-allowed',
            color: refreshable.length ? 'var(--text-primary)' : 'var(--text-faint)',
          }}>
          {refreshState && refreshState.done < refreshState.total
            ? `Refreshing ${refreshState.done + 1}/${refreshState.total}…`
            : `Refresh imported (${refreshable.length})`}
        </button>
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
        Hosts on the backend allowlist can be imported with one click —
        the fetch happens server-side through an SSRF-guarded path.  Adding
        a custom seed auto-allowlists its host.
      </div>

      {adding && (
        <AddSeedForm
          onCancel={() => { setAdding(false); setAddError(null); }}
          onSubmit={addCustomSeed}
          error={addError}
        />
      )}

      {refreshState && refreshState.done >= refreshState.total && (
        <div style={{
          fontSize: 12, padding: 10, borderRadius: 6, marginBottom: 12,
          background: refreshState.summary.failed.length ? 'var(--amber-light)' : 'var(--accent-light)',
          color: refreshState.summary.failed.length ? 'var(--amber)' : 'var(--accent)',
        }}>
          Refresh complete: {refreshState.summary.unchanged} unchanged,{' '}
          {refreshState.summary.replaced.length} updated
          {refreshState.summary.replaced.length > 0 && (
            <> (<em>{refreshState.summary.replaced.join('; ')}</em>)</>
          )}
          {refreshState.summary.failed.length > 0 && (
            <>, {refreshState.summary.failed.length} failed
              {' ('}
              <em>{refreshState.summary.failed.join('; ')}</em>
              {')'}</>
          )}
          .
        </div>
      )}
      {allowedError && (
        <div style={{
          fontSize: 12, color: 'var(--red)', background: 'var(--red-light)',
          padding: 8, borderRadius: 6, marginBottom: 12,
        }}>
          {allowedError}
        </div>
      )}
      {seedsLoadError && (
        <div style={{
          fontSize: 12, color: 'var(--red)', background: 'var(--red-light)',
          padding: 8, borderRadius: 6, marginBottom: 12,
        }}>
          {seedsLoadError}
        </div>
      )}

      {hidden.length > 0 && (
        <div style={{
          border: '1px dashed var(--border)', borderRadius: 8,
          marginBottom: 16, background: 'var(--bg-card)',
        }}>
          <button type="button"
            onClick={() => setShowHidden((v) => !v)}
            style={{
              width: '100%', textAlign: 'left',
              background: 'transparent', border: 0, cursor: 'pointer',
              padding: '10px 16px', fontSize: 13, color: 'var(--text-muted)',
            }}>
            {showHidden ? '▾' : '▸'}{' '}
            Hidden defaults ({hidden.length})
            <span style={{ marginLeft: 8, fontSize: 11 }}>
              {showHidden ? 'click to collapse' : 'click to view & restore'}
            </span>
          </button>
          {showHidden && (
            <ul style={{ margin: 0, padding: '0 16px 12px', listStyle: 'none', display: 'grid', gap: 4 }}>
              {hidden.map((s) => (
                <li key={s.id} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '6px 0', borderTop: '1px solid var(--border)',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer"
                      style={{ color: 'var(--text-muted)' }}>
                      {s.title}
                    </a>
                    <div style={{ color: 'var(--text-faint)', fontSize: 12 }}>
                      {s.group_label} · {s.scope}/{s.category}
                    </div>
                  </div>
                  <button type="button"
                    onClick={() => restoreSeed(s)}
                    title="Bring this default back into the active list."
                    style={{
                      background: 'var(--bg-card)', border: '1px solid var(--border)',
                      color: 'var(--text-secondary)',
                      borderRadius: 6, padding: '4px 10px', fontSize: 12,
                      cursor: 'pointer',
                    }}>
                    Restore
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {seedGroups.map((group) => (
        <div key={group.label} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginTop: 8 }}>
            {group.label}
          </div>
          {group.hint && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              {group.hint}
            </div>
          )}
          {group.note && (
            <div style={{
              fontSize: 12, color: 'var(--amber)', background: 'var(--amber-light)',
              padding: 8, borderRadius: 6, marginBottom: 8,
            }}>
              {group.note}
            </div>
          )}
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 6 }}>
            {group.seeds.map((s) => {
              const blockedReason = importableReason(s.url);
              const manualOnly = !!s.manual_only;
              const importable = !manualOnly && blockedReason === null;
              const status = busy[s.url];
              const alreadyImported = importedSet.has(s.url);
              const disabled = !importable || status === 'pending';
              const buttonLabel = (
                manualOnly             ? 'Manual upload'
                : status === 'pending' ? 'Importing…'
                : status === 'done'    ? 'Imported'
                : status === 'error'   ? 'Retry'
                : alreadyImported      ? 'Re-import'
                : 'Import'
              );
              return (
                <li key={s.id} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '6px 0', borderBottom: '1px solid var(--border)',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <a href={s.url} target="_blank" rel="noopener noreferrer">
                        {s.title}
                      </a>
                      {alreadyImported && (
                        <span title="This URL is already in your corpus."
                          style={{
                            fontSize: 11, padding: '1px 6px', borderRadius: 10,
                            color: 'var(--accent)', background: 'var(--accent-light)',
                            border: '1px solid var(--border-mid)',
                          }}>
                          ✓ Imported
                        </span>
                      )}
                      {s.is_custom && (
                        <span title="Custom seed (added by you)."
                          style={{
                            fontSize: 11, padding: '1px 6px', borderRadius: 10,
                            color: 'var(--blue)', background: 'var(--blue-light)',
                            border: '1px solid var(--blue-light)',
                          }}>
                          Custom
                        </span>
                      )}
                    </div>
                    <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      {s.why} <em>({s.scope}/{s.category})</em>
                    </div>
                    {errors[s.url] && (
                      <div style={{ color: 'var(--red)', fontSize: 12 }}>
                        {errors[s.url]}
                      </div>
                    )}
                    {notices[s.url] && !errors[s.url] && (
                      <div style={{ color: 'var(--accent)', fontSize: 12 }}>
                        {notices[s.url]}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    title={
                      manualOnly
                        ? 'Bot-blocked source — open the link, save the page from your browser, then upload via the file uploader above.'
                        : (blockedReason || (alreadyImported
                          ? 'Re-fetch to check for upstream changes.'
                          : ''))
                    }
                    onClick={() => importable && importSeed(s)}
                    disabled={disabled}
                    style={{
                      background: status === 'done' ? 'var(--accent-light)'
                        : alreadyImported ? 'var(--bg-secondary)' : 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      borderRadius: 6, padding: '4px 10px', fontSize: 12,
                      color: !importable ? 'var(--text-faint)' : 'var(--text-primary)',
                      cursor: disabled ? 'not-allowed' : 'pointer',
                    }}>
                    {buttonLabel}
                  </button>
                  <button
                    type="button"
                    onClick={() => removeSeed(s)}
                    aria-label={s.is_custom ? `Remove ${s.title || 'this seed'}` : `Hide ${s.title || 'this seed'}`}
                    title={s.is_custom ? 'Remove this custom seed.' : 'Hide this default from the list (you can restore it later).'}
                    style={{
                      background: 'transparent', border: 'none',
                      color: 'var(--text-faint)', cursor: 'pointer', fontSize: 16,
                      padding: '0 4px',
                    }}>
                    <span aria-hidden="true">×</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}


function AddSeedForm({ onCancel, onSubmit, error }) {
  const [form, setForm] = useState({
    title: '',
    url: '',
    scope: 'external',
    category: 'investing',
    why: '',
    group_label: 'Custom',
    manual_only: false,
  });

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setBool = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.checked }));

  const submit = (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.url.trim()) return;
    onSubmit(form);
  };

  return (
    <form onSubmit={submit} style={{
      border: '1px solid var(--border)', borderRadius: 8, padding: 12,
      background: 'var(--bg-card)', color: 'var(--text-primary)',
      marginBottom: 12, display: 'grid', gap: 8,
      gridTemplateColumns: '1fr 1fr',
    }}>
      <label style={{ gridColumn: '1 / -1', display: 'grid', gap: 4, fontSize: 12 }}>
        <span>Title</span>
        <input type="text" required value={form.title} onChange={set('title')}
          placeholder="e.g. Bogleheads Forum — Coin-flip allocation thread" />
      </label>
      <label style={{ gridColumn: '1 / -1', display: 'grid', gap: 4, fontSize: 12 }}>
        <span>URL (https://)</span>
        <input type="url" required value={form.url} onChange={set('url')}
          placeholder="https://www.example.com/article" />
      </label>
      <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
        <span>Scope</span>
        <select value={form.scope} onChange={set('scope')}>
          <option value="external">External (reference)</option>
          <option value="personal">Personal</option>
        </select>
      </label>
      <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
        <span>Category</span>
        <select value={form.category} onChange={set('category')}>
          <option value="tax">Tax</option>
          <option value="credit">Credit / debt</option>
          <option value="investing">Investing / retirement</option>
          <option value="literacy">General literacy</option>
        </select>
      </label>
      <label style={{ gridColumn: '1 / -1', display: 'grid', gap: 4, fontSize: 12 }}>
        <span>Why (shown under the title)</span>
        <input type="text" value={form.why} onChange={set('why')}
          placeholder="One-line reason this is worth citing." />
      </label>
      <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
        <span>Group label</span>
        <input type="text" value={form.group_label} onChange={set('group_label')}
          placeholder="Custom" />
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <input type="checkbox" checked={form.manual_only} onChange={setBool('manual_only')} />
        <span>Manual upload only (don't try to URL-fetch)</span>
      </label>

      {error && (
        <div style={{ gridColumn: '1 / -1', color: 'var(--red)', fontSize: 12 }}>
          {error}
        </div>
      )}

      <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" onClick={onCancel} style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          color: 'var(--text-secondary)',
          borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer',
        }}>Cancel</button>
        <button type="submit" style={{
          background: 'var(--accent)', color: '#fff', border: 0,
          borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer',
        }}>Add seed</button>
      </div>
    </form>
  );
}
