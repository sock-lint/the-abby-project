export function sharedAssetsRequired(value) {
  if (value === undefined || value === 'false') return false;
  if (value === 'true') return true;
  throw new Error('ABBY_SHARED_ASSETS_REQUIRED must be true or false');
}

export const SHARED_ASSET_SECRET_NAMES = Object.freeze([
  'ABBY_ASSETS_S3_ENDPOINT', 'ABBY_ASSETS_S3_REGION', 'ABBY_ASSETS_S3_BUCKET',
  'ABBY_ASSETS_S3_PREFIX', 'ABBY_SHARED_ASSETS_REQUIRED',
  'ABBY_ASSETS_ACCESS_KEY_ID', 'ABBY_ASSETS_SECRET_ACCESS_KEY', 'ABBY_ASSETS_SESSION_TOKEN',
]);

// Map this app's dedicated read-only key only inside the shared-assets Node
// process. Earlier image stages keep their existing generic AWS credentials.
export function sharedAssetsEnvironment(environment) {
  const result = { ...environment };
  const credentialNames = ['ABBY_ASSETS_ACCESS_KEY_ID', 'ABBY_ASSETS_SECRET_ACCESS_KEY', 'ABBY_ASSETS_SESSION_TOKEN'];
  if (!credentialNames.some((name) => environment[name] !== undefined)) return result;
  for (const name of credentialNames.slice(0, 2)) {
    if (typeof environment[name] !== 'string' || !environment[name].trim()) {
      throw new Error('Both ABBY_ASSETS_ACCESS_KEY_ID and ABBY_ASSETS_SECRET_ACCESS_KEY must be nonempty when dedicated shared credentials are provided');
    }
  }
  result.AWS_ACCESS_KEY_ID = environment.ABBY_ASSETS_ACCESS_KEY_ID.trim();
  result.AWS_SECRET_ACCESS_KEY = environment.ABBY_ASSETS_SECRET_ACCESS_KEY.trim();
  const token = environment.ABBY_ASSETS_SESSION_TOKEN;
  if (token !== undefined && (typeof token !== 'string' || !token.trim())) {
    throw new Error('ABBY_ASSETS_SESSION_TOKEN must be nonempty when provided');
  }
  if (token !== undefined) result.AWS_SESSION_TOKEN = token.trim();
  else delete result.AWS_SESSION_TOKEN;
  // The installed Node SDK prefers AWS_PROFILE to environment credentials.
  // A dedicated build key must not inherit an unrelated local/container profile.
  delete result.AWS_PROFILE;
  delete result.AWS_DEFAULT_PROFILE;
  return result;
}
