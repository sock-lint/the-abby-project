/** A previous account's late response must never decorate the current account. */
export function identityForUser(identity, user) {
  return user?.id != null && identity?.id != null && String(identity.id) === String(user.id) ? identity : null;
}
