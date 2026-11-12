// A display scope is bound to the verified session; it never changes roles.
let activeSpace = 'family';
let activeToken = '';

export function setRequestSpace(space, token) {
  activeSpace = space === 'personal' ? 'personal' : 'family';
  activeToken = token || '';
}

export function requestSpace(token) {
  return token && token === activeToken ? activeSpace : 'family';
}
