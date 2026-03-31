/**
 * StorageManager — sessionStorage with IndexedDB fallback.
 * Same API surface whether using sessionStorage or IndexedDB.
 * Transparent to the app layer.
 */

const StorageManager = (() => {
  const DB_NAME    = 'storyforge_storage';
  const STORE_NAME = 'kv';
  const DB_VERSION = 1;

  let _db            = null;
  let _usingFallback = false;
  let _sessionOk     = true;

  /* ── IndexedDB helpers ── */

  function _openDB() {
    return new Promise((resolve, reject) => {
      let req;
      try { req = indexedDB.open(DB_NAME, DB_VERSION); }
      catch (e) { return reject(e); }
      req.onupgradeneeded = (ev) => {
        const db = ev.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME))
          db.createObjectStore(STORE_NAME, { keyPath: 'key' });
      };
      req.onsuccess = (ev) => resolve(ev.target.result);
      req.onerror   = (ev) => reject(ev.target.error);
      req.onblocked = ()   => reject(new Error('IndexedDB blocked'));
    });
  }

  function _idbGet(key) {
    return new Promise((resolve, reject) => {
      if (!_db) return resolve(null);
      const req = _db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).get(key);
      req.onsuccess = (ev) => resolve(ev.target.result ? ev.target.result.value : null);
      req.onerror   = (ev) => reject(ev.target.error);
    });
  }

  function _idbSet(key, value) {
    return new Promise((resolve, reject) => {
      if (!_db) return reject(new Error('IndexedDB not open'));
      const req = _db.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME).put({ key, value });
      req.onsuccess = () => resolve();
      req.onerror   = (ev) => reject(ev.target.error);
    });
  }

  function _idbDelete(key) {
    return new Promise((resolve, reject) => {
      if (!_db) return resolve();
      const req = _db.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME).delete(key);
      req.onsuccess = () => resolve();
      req.onerror   = (ev) => reject(ev.target.error);
    });
  }

  function _idbClear() {
    return new Promise((resolve, reject) => {
      if (!_db) return resolve();
      const req = _db.transaction(STORE_NAME, 'readwrite').objectStore(STORE_NAME).clear();
      req.onsuccess = () => resolve();
      req.onerror   = (ev) => reject(ev.target.error);
    });
  }

  function _probeSession() {
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
    async init() {
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
        console.warn('[StorageManager] IndexedDB open failed:', e.message);
        _db = null;
      }
    },

    /**
     * Store a value. Tries sessionStorage; on QuotaExceededError falls back to IndexedDB.
     * @param {string} key
     * @param {string} value  Caller must JSON.stringify if needed.
     */
    async setItem(key, value) {
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
            console.warn('[StorageManager] sessionStorage.setItem unexpected error:', e.message);
          // fall through to IndexedDB
        }
      }

      if (_db) {
        try {
          await _idbSet(key, value);
          _usingFallback = true;
        } catch (e) {
          console.warn('[StorageManager] IndexedDB setItem failed:', e.message);
        }
      } else {
        console.warn('[StorageManager] No storage backend available for key:', key);
      }
    },

    /**
     * Retrieve a value. Checks sessionStorage first, then IndexedDB.
     * @param {string} key
     * @returns {Promise<string|null>}
     */
    async getItem(key) {
      if (_sessionOk) {
        try {
          const val = sessionStorage.getItem(key);
          if (val !== null) return val;
        } catch (e) {
          console.warn('[StorageManager] sessionStorage.getItem error:', e.message);
        }
      }
      if (_db) {
        try { return await _idbGet(key); }
        catch (e) { console.warn('[StorageManager] IndexedDB getItem failed:', e.message); }
      }
      return null;
    },

    /** Remove a key from both backends. */
    async removeItem(key) {
      if (_sessionOk) { try { sessionStorage.removeItem(key); } catch (_) {} }
      if (_db) {
        try { await _idbDelete(key); }
        catch (e) { console.warn('[StorageManager] IndexedDB removeItem failed:', e.message); }
      }
    },

    /** Clear all entries from both backends. */
    async clear() {
      if (_sessionOk) { try { sessionStorage.clear(); } catch (_) {} }
      if (_db) {
        try { await _idbClear(); }
        catch (e) { console.warn('[StorageManager] IndexedDB clear failed:', e.message); }
      }
      _usingFallback = false;
    },

    /** Returns true if the last write used IndexedDB instead of sessionStorage. */
    isUsingFallback() { return _usingFallback; },
  };
})();

window.storageManager = StorageManager;
