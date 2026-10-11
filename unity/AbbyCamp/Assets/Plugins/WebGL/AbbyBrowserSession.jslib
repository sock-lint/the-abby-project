// Same-origin handoff from the journal's existing browser session. This bridge
// never stores credentials or treats the cached user as proof of authentication.
mergeInto(LibraryManager.library, {
  AbbySession_ReadToken__deps: ['$lengthBytesUTF8', '$stringToUTF8', 'malloc'],
  AbbySession_ReadToken: function () {
    var token = '';
    try {
      var stored = window.localStorage.getItem('abby_auth_token');
      if (typeof stored === 'string' && /^[0-9a-f]{40}$/i.test(stored)) token = stored;
    } catch (_) {
      // Browser privacy/storage restrictions leave the player disconnected.
    }
    // IL2CPP frees returned strings allocated with malloc after marshaling.
    var size = lengthBytesUTF8(token) + 1;
    var buffer = _malloc(size);
    stringToUTF8(token, buffer, size);
    return buffer;
  },

  AbbySession_ClearToken__deps: ['$UTF8ToString'],
  AbbySession_ClearToken: function (expectedTokenPtr) {
    try {
      var expected = expectedTokenPtr ? UTF8ToString(expectedTokenPtr) : '';
      if (!/^[0-9a-f]{40}$/i.test(expected)) return;
      var storage = window.localStorage;
      // A stale request from the previous account must not clear a newer login.
      if (storage.getItem('abby_auth_token') !== expected) return;
      storage.removeItem('abby_auth_token');
      storage.removeItem('auth:last-user');
    } catch (_) {
      // Clearing browser state is best effort; the API remains authoritative.
    }
  },

  AbbySession_OpenJournal: function () {
    window.location.assign('/chronicle?tab=journal');
  },

  AbbySession_OpenDestination__deps: ['$UTF8ToString'],
  AbbySession_OpenDestination: function (pathPtr) {
    // Defense at the browser boundary as well as Unity's typed navigation.
    // These exact root-relative routes carry no tokens or arbitrary URLs.
    var allowed = [
      '/', '/chronicle?tab=journal', '/chronicle?tab=grades', '/quests',
      '/treasury?tab=bazaar', '/treasury?tab=satchel', '/bestiary',
      '/bestiary?tab=hatchery', '/bestiary?tab=companions',
      '/bestiary?tab=mounts', '/bestiary?tab=codex',
      '/quests?tab=study', '/quests?tab=duties', '/quests?tab=rituals',
      '/quests?tab=movement', '/quests?tab=ventures', '/quests?tab=forge',
      '/quests?tab=trials', '/atlas?tab=skills', '/atlas?tab=badges',
      '/atlas?tab=lorebook', '/sigil', '/chronicle?tab=yearbook',
      '/chronicle?tab=sketchbook', '/treasury?tab=wages',
      '/treasury?tab=coffers', '/treasury?tab=hoards'
    ];
    try {
      var target = pathPtr ? UTF8ToString(pathPtr) : '';
      if (allowed.indexOf(target) < 0) return 0;
      window.location.assign(target);
      return 1;
    } catch (_) {
      return 0;
    }
  }
});
