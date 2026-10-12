// Native configuration deliberately comes from explicit shell variables.
// Do not inherit an existing web .env file or default to the production API.
export function nativeBuildConfig(env) {
  if (env.ABBY_NATIVE_ENVIRONMENT !== 'staging') {
    throw new Error('Set ABBY_NATIVE_ENVIRONMENT=staging for this development prototype.');
  }
  let url;
  try { url = new URL(env.ABBY_NATIVE_API_ORIGIN); } catch {
    throw new Error('Set ABBY_NATIVE_API_ORIGIN to your isolated HTTPS staging origin.');
  }
  if (url.protocol !== 'https:' || url.username || url.password
    || url.pathname !== '/' || url.search || url.hash
    || ['abby.bos.lol', 'www.abby.bos.lol'].includes(url.hostname.toLowerCase())) {
    throw new Error('The native prototype accepts only a credential-free HTTPS staging origin; production is excluded.');
  }
  return {
    base: '/',
    outDir: 'dist-native',
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(url.origin),
      'import.meta.env.VITE_NATIVE_BUILD': JSON.stringify('true'),
      'import.meta.env.VITE_NATIVE_ENVIRONMENT': JSON.stringify('staging'),
    },
  };
}
