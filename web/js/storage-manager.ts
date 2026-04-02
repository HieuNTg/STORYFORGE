/**
 * StorageManager — sessionStorage with IndexedDB fallback.
 * Same API surface whether using sessionStorage or IndexedDB.
 * Transparent to the app layer.
 */

const _StorageManager = ((): StorageManagerInterface => {
  const DB_NAME    = 'storyforge_storage';
  const STORE_NAME = 'kv';
  const DB_VERSION = 1;

  let _db:            IDBDatabase | null = null;
  let _usingFallback: boolean            = false;
  let _sessionOk:     boolean            = true;

  /* ── IndexedDB helpers ── */

  function _openDB(): Promise<IDBDatabase> {
    return new Promise<IDBDatabase>((resolve, reject) => {
      let req: IDBOpenDBRequest;
      try { req = indexedDB.open(DB_NAME, DB_VERSION); }
      catch (e) { return reject(e); }
      req.onupgradeneeded = (ev: IDBVersionChangeEvent) => {
        const db = (ev.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(STORE_NAME))
          db.createObjectStore(STORE_NAME, { keyPath: 'key' });
      };
      req.onsuccess = (ev: Event) => resolve((ev.target as IDBOpenDBRequest).result);
      req.onerror   = (ev: Event) => reject((ev.target as IDBOpenDBRequest).error);
      req.onblocked = ()          => reject(new Error('IndexedDB blocked'));
    });
  }

  function _idbGet(key: string): Promise<string | null> {
    return new Promise<string | null>((resolve, reject) => {
      if (!_db) return resolve(null);
      const req: IDBRequest<{ key: string; value: string } | undefined> =
        _db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).get(key);
      req.onsuccess = (ev: Event) => {
        const record = (ev.target as IDBRequest<{ key: string; value: string } | undefined>).result;
        resolve(record ? record.value : null);
      };
      req.onerror = (ev: Event) => reject((ev.target as IDBRequest).error);
    });
  }

  function _idbSet(key: string, value: string): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      if (!_db) return reject(new Error('IndexedDB not open'));
      const req: IDBRequest = _db.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME).put({ key, value });
      req.onsuccess = () => resolve();
      req.onerror   = (ev: Event) => reject((ev.target as IDBRequest).error);
    });
  }

  function _idbDelete(key: string): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      if (!_db) return resolve();
      const req: IDBRequest = _db.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME).delete(key);
      req.onsuccess = () => resolve();
      req.onerror   = (ev: Event) => reject((ev.target as IDBRequest).error);
    });
  }

  function _idbClear(): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      if (!_db) return resolve();
      const req: IDBRequest = _db.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME).clear();
      req.onsuccess = () => resolve();
      req.onerror   = (ev: Event) => reject((ev.target as IDBRequest).error);
    });
  }

  function _probeSession(): boolean {
    try {
      sessionStorage.setItem('__sf_probe__', '1');
      sessionStorage.removeItem('__sf_probe__');
      return true;
    } catch (_) { return false; }
  }

  /* ── Public API ── */

  return {
    /**
     * Probe sessionStorage and open IndexedDB as standby fallback.
     * Safe to call multiple times — no-op after first successful open.
     */
    async init(): Promise<void> {
      _sessionOk = _probeSession();
      if (!_sessionOk)
        console.warn('[StorageManager] sessionStorage unavailable, using IndexedDB only.');

      if (typeof indexedDB === 'undefined') {
        console.warn('[StorageManager] IndexedDB unavailable. Storage is best-effort.');
        return;
      }
      if (_db) return; // already open

      try {
        _db = await _openDB();
      } catch (e) {
        console.warn('[StorageManager] IndexedDB open failed:', (e as Error).message);
        _db = null;
      }
    },

    /**
     * Store a value. Tries sessionStorage; on QuotaExceededError falls back to IndexedDB.
     * @param key
     * @param value  Caller must JSON.stringify if needed.
     */
    async setItem(key: string, value: string): Promise<void> {
      if (_sessionOk) {
        try {
          sessionStorage.setItem(key, value);
          _usingFallback = false;
          return;
        } catch (e) {
          const isQuota = e instanceof DOMException && (
            e.code === 22 ||
            e.name === 'QuotaExceededError' ||
            e.name === 'NS_ERROR_DOM_QUOTA_REACHED'
          );
          if (!isQuota)
            console.warn('[StorageManager] sessionStorage.setItem unexpected error:', (e as Error).message);
          // fall through to IndexedDB
        }
      }

      if (_db) {
        try {
          await _idbSet(key, value);
          _usingFallback = true;
        } catch (e) {
          console.warn('[StorageManager] IndexedDB setItem failed:', (e as Error).message);
        }
      } else {
        console.warn('[StorageManager] No storage backend available for key:', key);
      }
    },

    /**
     * Retrieve a value. Checks sessionStorage first, then IndexedDB.
     * @param key
     * @returns The stored string value, or null if not found.
     */
    async getItem(key: string): Promise<string | null> {
      if (_sessionOk) {
        try {
          const val = sessionStorage.getItem(key);
          if (val !== null) return val;
        } catch (e) {
          console.warn('[StorageManager] sessionStorage.getItem error:', (e as Error).message);
        }
      }
      if (_db) {
        try { return await _idbGet(key); }
        catch (e) { console.warn('[StorageManager] IndexedDB getItem failed:', (e as Error).message); }
      }
      return null;
    },

    /** Remove a key from both backends. */
    async removeItem(key: string): Promise<void> {
      if (_sessionOk) { try { sessionStorage.removeItem(key); } catch (_) {} }
      if (_db) {
        try { await _idbDelete(key); }
        catch (e) { console.warn('[StorageManager] IndexedDB removeItem failed:', (e as Error).message); }
      }
    },

    /** Clear all entries from both backends. */
    async clear(): Promise<void> {
      if (_sessionOk) { try { sessionStorage.clear(); } catch (_) {} }
      if (_db) {
        try { await _idbClear(); }
        catch (e) { console.warn('[StorageManager] IndexedDB clear failed:', (e as Error).message); }
      }
      _usingFallback = false;
    },

    /** Returns true if the last write used IndexedDB instead of sessionStorage. */
    isUsingFallback(): boolean { return _usingFallback; },
  };
})();

window.storageManager = _StorageManager;
