// The installed vite-plugin-pwa prompt client reloads on Workbox controlling
// even when passed false. Register the existing generated worker directly so
// PwaStatusProvider owns every reload and can protect dirty/busy work.
export function registerPromptWorker({ onNeedRefresh, onOfflineReady, onRegisterError } = {}) {
  let disposed = false;
  const cleanups = [];
  const watched = new WeakSet();
  const container = typeof navigator !== 'undefined' ? navigator.serviceWorker : null;

  const listen = (target, event, callback) => {
    target.addEventListener(event, callback);
    cleanups.push(() => target.removeEventListener(event, callback));
  };

  const registration = !container?.register ? Promise.resolve(null)
    : Promise.resolve().then(() => container.register('/sw.js', { scope: '/' })).then((registered) => {
      if (disposed || !registered) return null;
      if (registered.waiting) onNeedRefresh?.();
      const watchInstalling = () => {
        const worker = registered.installing;
        if (!worker || watched.has(worker)) return;
        watched.add(worker);
        const replacing = Boolean(container.controller || registered.active);
        const installed = () => {
          if (disposed || worker.state !== 'installed') return;
          if (replacing) onNeedRefresh?.();
          else onOfflineReady?.();
        };
        listen(worker, 'statechange', installed);
        installed();
      };
      listen(registered, 'updatefound', watchInstalling);
      watchInstalling();
      return registered;
    }).catch((error) => {
      if (!disposed) onRegisterError?.(error);
      return null;
    });

  return {
    async update() {
      const registered = await registration;
      if (disposed || !registered?.waiting) return false;
      try {
        registered.waiting.postMessage({ type: 'SKIP_WAITING' });
        return true;
      } catch (error) {
        onRegisterError?.(error);
        return false;
      }
    },
    dispose() {
      disposed = true;
      cleanups.splice(0).forEach((cleanup) => cleanup());
    },
  };
}
